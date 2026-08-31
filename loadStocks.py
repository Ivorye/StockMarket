import pymysql, pandas as pd, tushare as ts, time, datetime

TUSHARE_TOKEN = "4d47c02a8bb025881c9dd9e3c36d25139ab5b429a73353e566fc02a9"

#返回数据库连接。需要依赖本地已建立数据库schema（stockshare）
def connectDB():
	db=pymysql.connect(host='localhost',
		user='root',
		password='P@ssw0rd',
		database='stockshare',connect_timeout=10,read_timeout=30,write_timeout=30)
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
	db=connectDB()
	cursor=db.cursor()
	cursor.execute("CREATE TABLE IF NOT EXISTS st_daily (ts_code VARCHAR(12) NOT NULL,symbol VARCHAR(6) NOT NULL,trade_date VARCHAR(8) NOT NULL,openp FLOAT,high FLOAT,low FLOAT,closep FLOAT,preclose FLOAT,changes FLOAT,pct_chg FLOAT,vol FLOAT,amount FLOAT,PRIMARY KEY (ts_code,trade_date),INDEX idx_trade_date (trade_date),INDEX idx_symbol (symbol))")
	db.commit()
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
		ln=len(data)
		sql="INSERT INTO st_daily(ts_code,symbol,trade_date,openp,high,low,closep,preclose,changes,pct_chg,vol,amount) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE openp=VALUES(openp),high=VALUES(high),low=VALUES(low),closep=VALUES(closep),preclose=VALUES(preclose),changes=VALUES(changes),pct_chg=VALUES(pct_chg),vol=VALUES(vol),amount=VALUES(amount)"
		for i in range(0,ln):
			try:
					cursor.execute(sql, (df.loc[k].ts_code,df.loc[k].symbol,
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
	cursor.execute("SELECT a.symbol FROM st_daily a JOIN st_daily b ON b.ts_code=a.ts_code WHERE a.trade_date=%s AND b.trade_date=%s AND b.closep>a.closep*(1+%s/100)",(start_date,end_date,rate))
	lst=[r[0] for r in cursor.fetchall()]
	db.close()
	return lst


# 增量加载日线数据：按交易日批量获取全市场数据并批量入库。
# 检查最近 lookback_days 天，仅处理数据库最新交易日之后的数据。
def incrementalUpdateDailyData(df=None, lookback_days=30):
	if(df is None or len(df)==0):
		return
	today=datetime.date.today()
	today_str=today.strftime('%Y%m%d')
	start_str=(today-datetime.timedelta(days=lookback_days)).strftime('%Y%m%d')
	db=connectDB()
	cursor=db.cursor()
	pro=ts.pro_api(TUSHARE_TOKEN)
	try:
		# dailyUpdate 入口已确认今天是交易日。这里不再次调用低额度 trade_cal API；
		# 历史节假日作为候选日期调用 daily 时会返回空集，可安全跳过。
		trade_dates=[]
		candidate=today-datetime.timedelta(days=lookback_days)
		while candidate<=today:
			if candidate.weekday()<5:
				trade_dates.append(candidate.strftime('%Y%m%d'))
			candidate+=datetime.timedelta(days=1)

		cursor.execute("SELECT MAX(trade_date) FROM st_daily")
		latest_date=cursor.fetchone()[0]
		# 只获取最新入库日之后的工作日；历史节假日和停牌不会被反复误判为缺口。
		pending_dates=[d for d in trade_dates if not latest_date or d>latest_date]
		print(time.ctime(),'batch daily update: %d candidate days checked, %d pending, latest=%s'%(
			len(trade_dates),len(pending_dates),latest_date))

		sql="INSERT INTO st_daily(ts_code,symbol,trade_date,openp,high,low,closep,preclose,changes,pct_chg,vol,amount) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE symbol=VALUES(symbol),openp=VALUES(openp),high=VALUES(high),low=VALUES(low),closep=VALUES(closep),preclose=VALUES(preclose),changes=VALUES(changes),pct_chg=VALUES(pct_chg),vol=VALUES(vol),amount=VALUES(amount)"
		total_rows=0
		for trade_date in pending_dates:
			data=None
			for retry in range(3):
				try:
					data=pro.daily(trade_date=trade_date)
					break
				except Exception as e:
					print("API异常(重试%d/3) %s: %s"%(retry+1,trade_date,e))
					time.sleep(5)
			if data is None or data.empty:
				print(time.ctime(),trade_date,'returned no daily data')
				continue
			rows=[(
				str(row.ts_code),str(row.ts_code).split('.')[0],str(row.trade_date),
				float(row.open),float(row.high),float(row.low),float(row.close),
				float(row.pre_close),float(row.change),float(row.pct_chg),
				float(row.vol),float(row.amount)
			) for row in data.itertuples(index=False)]
			cursor.executemany(sql,rows)
			db.commit()
			total_rows+=len(rows)
			print(time.ctime(),'%s: %d rows upserted'%(trade_date,len(rows)))
		print(time.ctime(),'batch daily update done: %d dates, %d rows'%(
			len(pending_dates),total_rows))
	finally:
		cursor.close()
		db.close()
