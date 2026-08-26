import pymysql, pandas as pd, tushare as ts, time, datetime

TUSHARE_TOKEN = "4d47c02a8bb025881c9dd9e3c36d25139ab5b429a73353e566fc02a9"

#返回数据库连接。需要依赖本地已建立数据库schema（stockshare）
def connectDB():
	db=pymysql.connect(host='localhost',
		user='root',
		password='P@ssw0rd',
		database='stockshare')
	return db

def _escape_table_name(name):
	"""用反引号包裹表名，防止SQL关键字冲突"""
	return "`%s`" % name.replace('`', '')

def _check_execution_status(task_name):
	"""检查任务是否已成功执行过"""
	try:
		db=connectDB()
		cursor=db.cursor()
		cursor.execute("SELECT status FROM st_execution_status WHERE task_name=%s",(task_name,))
		row=cursor.fetchone()
		cursor.close();db.close()
		return row and row[0]=='Y'
	except Exception:
		return False

def _update_execution_status(task_name, status='Y'):
	"""更新任务执行状态"""
	try:
		db=connectDB()
		cursor=db.cursor()
		today=datetime.date.today().strftime('%Y%m%d')
		sql="INSERT INTO st_execution_status(task_name,exec_date,status) VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE exec_date=%s,status=%s"
		cursor.execute(sql,(task_name,today,status,today,status))
		db.commit()
		cursor.close();db.close()
	except Exception as e:
		print(f'更新执行状态失败: {e}')

#获取最新股票列表（调tushare API），同时缓存到stocks表
#API失败时检查执行状态，状态为Y则直接从stocks表读取缓存
def getStockBasic():
	try:
		pro = ts.pro_api(TUSHARE_TOKEN)
		data = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,fullname,area,industry,list_date')
		df=pd.DataFrame(data)
		_store_to_stocks(df)
		_update_execution_status('stock_basic','Y')
		return df
	except Exception as e:
		if _check_execution_status('stock_basic'):
			print('tushare API失败，st_execution_status状态为Y，从stocks表读取缓存')
			return getStockBasicFromDB()
		print('tushare API失败且无成功执行记录: %s'%e)
		return getStockBasicFromDB()

def _store_to_stocks(df):
	db=connectDB()
	cursor=db.cursor()
	sql="INSERT IGNORE INTO stocks(id,symbol,st_code,fullname,list_date) VALUES(%s,%s,%s,%s,%s)"
	for i in range(len(df)):
		try:
			cursor.execute(sql,(i+1,df.iloc[i].symbol,df.iloc[i].ts_code,df.iloc[i].fullname,df.iloc[i].list_date))
		except Exception:
			pass
		if i%500==499:
			db.commit()
	db.commit()
	db.close()

#从数据库stocks表读取股票列表（避免重复调用stock_basic API）
#返回与getStockBasic相同结构的DataFrame，若表为空返回None
def getStockBasicFromDB():
	db=connectDB()
	cursor=db.cursor()
	cursor.execute("SELECT symbol, st_code AS ts_code, fullname, fullname AS name, list_date FROM stocks")
	rows = cursor.fetchall()
	db.close()
	if not rows:
		return None
	df = pd.DataFrame(rows, columns=['symbol','ts_code','fullname','name','list_date'])
	return df

#获取stock_basic里面的股票列表，为每支股票创建历史记录表
#open、close、change是SQL关键字，列名使用openp、closep、changes替代
def createStockTable(df=None):
	l=len(df)
	db=connectDB()
	cursor=db.cursor()
	for i in range(0,l):
		table=_escape_table_name("gp%s" % df.loc[i].symbol)
		sql="CREATE TABLE %s (" \
			"`trade_date` VARCHAR(8) NOT NULL," \
			"`openp` FLOAT NOT NULL," \
			"`high` FLOAT NOT NULL," \
			"`low` FLOAT NOT NULL," \
			"`closep` FLOAT NOT NULL," \
			"`preclose` FLOAT NOT NULL," \
			"`changes` FLOAT NOT NULL," \
			"`pct_chg` FLOAT NOT NULL," \
			"`vol` FLOAT NOT NULL," \
			"`amount` FLOAT NOT NULL," \
			"PRIMARY KEY (`trade_date`)," \
			"UNIQUE INDEX `trade_date_UNIQUE` (`trade_date` ASC) VISIBLE)" % table
		try:
			cursor.execute(sql)
			if i % 50 == 0:
				print(i, " tables have been created")
			if i == l-1:
				print(i, " All tables have been created")
		except Exception as e:
			print("建表异常 %s: %s" % (df.loc[i].symbol, e))
	db.close()


#将所有股票基本信息载入总表
def loadAllBasic(df=None):
	l=len(df)
	db=connectDB()
	cursor=db.cursor()
	for i in range(0,l):
		symbol=df.loc[i].symbol
		sql0="select count(*) from stocks where symbol=%s"
		sql="insert into stocks(id,symbol,st_code,fullname,list_date) values(%s,%s,%s,%s,%s)"
		cursor.execute(sql0, (symbol,))
		quantity = cursor.fetchone()[0]
		if quantity == 0:
			try:
				cursor.execute(sql, (i+1, df.loc[i].symbol, df.loc[i].ts_code, df.loc[i].fullname, df.loc[i].list_date))
				if i % 50 == 0:
					db.commit()
					print(i, " records have been loaded to database")
				if i == l-1:
					db.commit()
					print(i, " All records have been loaded to database")
			except Exception as e:
				print("插入基本信息异常 %s: %s" % (symbol, e))
				db.rollback()
	db.close()

#输入：DF数据帧，开始日期和结束日期。在此之间的交易记录导入数据库
def insertNewTransactonRecordForAllStocks(df=None,start_date='',end_date=''):
	l=len(df)
	db=connectDB()
	cursor=db.cursor()
	pro = ts.pro_api(TUSHARE_TOKEN)
	for k in range(0,l):
		try:
			data=pro.daily(ts_code=df.loc[k].ts_code,start_date=start_date,end_date=end_date)
		except Exception as e:
			print("获取日线数据异常 %s: %s" % (df.loc[k].ts_code, e))
			time.sleep(5)
			continue
		if data is None or len(data) == 0:
			continue
		table=_escape_table_name("gp%s" % df.loc[k].symbol)
		ln=len(data)
		for i in range(0,ln):
			sql0="select trade_date from %s where trade_date=%%s" % table
			sql="insert into %s(trade_date,openp,high,low,closep,preclose,changes,pct_chg,vol,amount) " \
				"values(%%s,%%s,%%s,%%s,%%s,%%s,%%s,%%s,%%s,%%s)" % table
			result=cursor.execute(sql0, (data.loc[i].trade_date,))
			if result==0:
				try:
					cursor.execute(sql, (
						data.loc[i].trade_date,
						float(data.loc[i].open),
						float(data.loc[i].high),
						float(data.loc[i].low),
						float(data.loc[i].close),
						float(data.loc[i].pre_close),
						float(data.loc[i].change),
						float(data.loc[i].pct_chg),
						float(data.loc[i].vol),
						float(data.loc[i].amount),
					))
					if i % 50 == 0:
						db.commit()
						print(i, " records have been loaded to database")
					if i == ln-1:
						db.commit()
						print(i, " All records have been loaded to database")
				except Exception as e:
					print("插入交易记录异常 %s %s: %s" % (df.loc[k].symbol, data.loc[i].trade_date, e))
					db.rollback()
		if k % 50 == 0:
			print(k, " tables have been processed")
		if k == l-1:
			print(k, " All tables have been processed")
		time.sleep(1.5)  # 限速：pro.daily()限制50次/分钟
	db.close()


#获取给定日期段内阶段涨幅大于rate的股票，返回一个股票列表list
def getJDZF(df='',start_date='',end_date='',rate=''):
	l=len(df)
	db=connectDB()
	cursor=db.cursor()
	lst=[]
	for i in range(0,l):
		symbol=df.loc[i].symbol
		table=_escape_table_name("gp%s" % symbol)
		sql="select closep from %s where trade_date=%%s" % table
		try:
			cursor.execute(sql, (start_date,))
			p1 = cursor.fetchall()
			cursor.execute(sql, (end_date,))
			p2 = cursor.fetchall()
			p3 = p1[0][0]
			p4 = p2[0][0]
			ratio=1+rate/100
			if p4>p3*ratio:
				lst.append(symbol)
			if i % 500 == 0:
				print(i, " records processed")
			if i == l-1:
				print(i, " All records processed")
		except Exception as e:
			print("查询涨幅异常 %s: %s" % (symbol, e))
	db.close()
	return lst


#增量加载日线数据：查询每张表最新日期，只补缺失天数
#带断层检测和失败重试
def incrementalUpdateDailyData(df=None, lookback_days=30):
	if(df is None or len(df)==0):
		return
	today_str=datetime.date.today().strftime('%Y%m%d')
	db=connectDB()
	cursor=db.cursor()
	pro=ts.pro_api(TUSHARE_TOKEN)
	total=len(df)
	updated=0
	skipped=0
	for k in range(total):
		sym=df.loc[k].symbol
		ts_code=df.loc[k].ts_code
		table=_escape_table_name("gp%s"%sym)
		#获取该表已有的所有日期（用于检测断层）
		try:
			cursor.execute("SELECT trade_date FROM %s ORDER BY trade_date"%table)
			existing=set(r[0] for r in cursor.fetchall())
		except Exception:
			existing=set()
		if existing:
			latest=max(existing)
			#检测断层：统计日期范围内的工作日数 vs 实际行数
			earliest=min(existing)
			span_days=int((datetime.datetime.strptime(latest,'%Y%m%d')-datetime.datetime.strptime(earliest,'%Y%m%d')).days)
			#工作日约为跨度天数的5/7，如果实际行数不到预期的80%，说明有断层
			expected_trading_days=int(span_days*5/7)
			if span_days>10 and len(existing)<expected_trading_days*0.8:
				#有断层，按缺失天数回溯（至少lookback_days，最多覆盖全部缺失）
				missing_days=expected_trading_days-len(existing)
				lookback=max(lookback_days,missing_days*2+30)
				start=(datetime.date.today()-datetime.timedelta(days=lookback)).strftime('%Y%m%d')
				print(time.ctime(),'%s: 检测到%d天断层，回溯%d天加载'%(sym,missing_days,lookback))
			elif latest>=today_str:
				skipped+=1
				if k%200==199:
					print(time.ctime(),k+1,'processed,',skipped,'up-to-date,',updated,'updated')
				continue
			else:
				start=(datetime.datetime.strptime(latest,'%Y%m%d')+datetime.timedelta(days=1)).strftime('%Y%m%d')
		else:
			start=(datetime.date.today()-datetime.timedelta(days=lookback_days)).strftime('%Y%m%d')
		#调用API获取数据
		data=None
		for retry in range(3):
			try:
				data=pro.daily(ts_code=ts_code,start_date=start,end_date=today_str)
				break
			except Exception as e:
				print("API异常(重试%d/3) %s: %s"%(retry+1,ts_code,e))
				time.sleep(5)
		if data is None or len(data)==0:
			skipped+=1
			if k%200==199:
				print(time.ctime(),k+1,'processed,',skipped,'up-to-date,',updated,'updated')
			continue
		#检测API返回的数据是否有大段断层（>10个交易日缺失）
		dates=sorted(data.trade_date.tolist())
		has_major_gap=False
		for i in range(len(dates)-1):
			d1=datetime.datetime.strptime(dates[i],'%Y%m%d')
			d2=datetime.datetime.strptime(dates[i+1],'%Y%m%d')
			if (d2-d1).days>15:
				print("警告 %s: API数据有断层 %s->%s"%(ts_code,dates[i],dates[i+1]))
				has_major_gap=True
				break
		#逐行插入（INSERT IGNORE跳过已有行，不影响其他行）
		sql="INSERT IGNORE INTO %s(trade_date,openp,high,low,closep,preclose,changes,pct_chg,vol,amount) " \
			"values(%%s,%%s,%%s,%%s,%%s,%%s,%%s,%%s,%%s,%%s)"%table
		inserted=0
		for i in range(len(data)):
			td=data.iloc[i].trade_date
			if td in existing:
				continue
			try:
				cursor.execute(sql,(
					td,
					float(data.iloc[i].open),
					float(data.iloc[i].high),
					float(data.iloc[i].low),
					float(data.iloc[i].close),
					float(data.iloc[i].pre_close),
					float(data.iloc[i].change),
					float(data.iloc[i].pct_chg),
					float(data.iloc[i].vol),
					float(data.iloc[i].amount),
				))
				if cursor.rowcount>0:
					inserted+=1
			except Exception as e:
				print("插入异常 %s %s: %s"%(sym,td,e))
		db.commit()
		updated+=1
		if inserted>0 or has_major_gap:
			print(time.ctime(),'%s: %d rows inserted, gap=%s'%(sym,inserted,has_major_gap))
		if k%200==199:
			print(time.ctime(),k+1,'processed,',skipped,'up-to-date,',updated,'updated')
		time.sleep(1.5)
	db.close()
	print(time.ctime(),'incrementalUpdate done: %d updated, %d up-to-date, %d total'%(updated,skipped,total))
