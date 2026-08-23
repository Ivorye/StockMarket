import tushare as ts
import openpyxl
from pandas import DataFrame
import time
import datetime
import mysql.connector

TUSHARE_TOKEN = '4d47c02a8bb025881c9dd9e3c36d25139ab5b429a73353e566fc02a9'

#延迟加载：优先从stocks表读取，回退到tushare API
_basic_cache = None
def _get_stock_basic():
	global _basic_cache
	if _basic_cache is not None:
		return _basic_cache
	#先从数据库读取
	try:
		mdb=_connect_sm()
		mycsr=mdb.cursor()
		mycsr.execute("SELECT COUNT(*) FROM stocks")
		cnt=mycsr.fetchone()[0]
		if cnt>0:
			mycsr.execute("SELECT st_code AS ts_code,symbol,fullname AS name,list_date FROM stocks")
			rows=mycsr.fetchall()
			df=DataFrame(rows,columns=['ts_code','symbol','name','list_date'])
			_basic_cache=df
			mycsr.close();mdb.close()
			return _basic_cache
		mycsr.close();mdb.close()
	except Exception:
		pass
	#回退到tushare API
	pro = ts.pro_api(TUSHARE_TOKEN)
	_basic_cache = pro.query('stock_basic')
	#缓存到stocks表
	_store_to_stocks(_basic_cache)
	return _basic_cache

def _store_to_stocks(df):
	mdb=_connect_sm()
	mycsr=mdb.cursor()
	sql="INSERT IGNORE INTO stocks(id,symbol,st_code,fullname,list_date) VALUES(%s,%s,%s,%s,%s)"
	for i in range(len(df)):
		try:
			mycsr.execute(sql,(i+1,df.iloc[i].symbol,df.iloc[i].ts_code,df.iloc[i].name,df.iloc[i].list_date))
		except Exception:
			pass
		if i%500==499:
			mdb.commit()
	mdb.commit()
	mycsr.close()
	mdb.close()

def _connect_sm():
	return mysql.connector.connect(host="localhost",user="root",passwd="P@ssw0rd",database='stockshare')

#通用筛选条件：剔除科创板(688)、ST、*ST、次新股(2021年后上市且上市晚于startDate)
def _should_skip(df, i, startDate=''):
	sym = df.symbol[i]
	name = df.name[i]
	lst = df.list_date[i]
	if sym[0:3] == '688':
		return True
	if name[0:2] == 'ST' or name[0:2] == '*S':
		return True
	#原逻辑：list_date < '20210101' AND list_date < startDate 两个条件同时满足才不排除
	if lst >= '20210101' and (not startDate or lst >= startDate):
		return True
	return False

#获取默认股票列表
def _default_stock_list():
	df = _get_stock_basic()
	return df.ts_code

#def myThread(threadName='', param=''):

def loadAllStockBasicsIntoMysql():
	pro = ts.pro_api(TUSHARE_TOKEN)
	df  = pro.query('stock_basic')
	stockList = df.ts_code
	l = len(stockList)
	mdb=_connect_sm()
	mycsr = mdb.cursor()
	sql = "insert into st_basic(ts_code,symbol,name,area,list_date) values(%s,%s,%s,%s,%s)"
	sql2= "select * from st_basic where ts_code=%s"
	counter=0
	print(time.ctime(),'-------- processing begin---------------')
#load all basic table data
	for i in range(len(df)):
		val2= (df.ts_code[i],)
		mycsr.execute(sql2,val2)
		rst=mycsr.fetchall()
		if(len(rst) ==0):
			tscode= df.ts_code[i]
			symbol= df.symbol[i]
			name  = df.name[i]
			area  = df.area[i]
			indst = df.industry[i]
			market= df.market[i]
			lstdte= df.list_date[i]
			val =(tscode,symbol,name,area,lstdte)
			mycsr.execute(sql,val)
			counter+=1
		if(i%100 == 99):
			print(round(i/100)*100, 'records processed...')
		if(i== len(df) -1):
			print('All', len(df), 'records processed! added ',counter,' new records')
	mdb.commit()
	mycsr.close()
	mdb.close()
	return stockList

#个股检测上涨动能算法：一个月内出现过单日6个点上涨的幅度(A日)。月底较月初上涨，A日过后振幅收窄且量缩（所有交易日的单日量没有一天超过A日总量），
#一个星期后可以买入，或等再一次涨幅超3个点时介入。

#选出迄今跳空过
def gettiaokongshangzhangguo(startDate='',endDate=''):
	if(startDate is None or startDate == ''):
		print('startDate must input')
		return []
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d",time.localtime())
		print('end date is:',endDate)
	df = _get_stock_basic()
	stockList = df.ts_code
	l = len(stockList)
	lstMultiple = []
	print(time.ctime(),'-------- processing begin---------------')
	for i in range(l):
		if (not _should_skip(df, i, startDate)):
			hangqing = ts.pro_bar(ts_code=df.ts_code[i], adj='qfq', start_date=startDate, end_date=endDate)
			if hangqing is None:
				continue
			idx = len(hangqing)
			if (idx > 3):
				x = 0
				for j in range(idx-1):
					volChange = ( hangqing.vol[j] / hangqing.vol[j + 1] )
					if (hangqing.close[0]>hangqing.close[idx-1]*1.3
					and (hangqing.low[j]>hangqing.high[j+1]
					or (hangqing.open[j+1]<hangqing.close[j+1]<hangqing.open[j]
					and volChange>2.5))):
						x = 1
						break
				if (x == 1):
					lstMultiple.append(df.ts_code[i])
					print(df.ts_code[i],j,hangqing.vol[j+1], hangqing.vol[j], round(volChange))
		if ( i % 100 == 99):
			print(time.ctime(), round(i/100)*100, ' records have been processed....')
		if ( i== l -1):
			print (time.ctime(), " All records have been processed!!!")
	print(time.ctime(),'-------- processing end-----------------')
	return lstMultiple

#选出曾经有过巨量上涨记录，第二三天量跌调整，但是振幅在2%以内的股票，------->很有效，选中股票莱美药业买入直赚10个点
def getJuliangshangzhang(stockList='',startDate='',endDate='',multiple=''):
	if(startDate is None or startDate == ''):
		print('startDate must input')
		return []
	if(multiple is None or multiple == ''):
		multiple = 2;print('multiple is ', multiple)
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d",time.localtime())
	if(stockList is None or stockList == ''):
		stockList = _default_stock_list()
	df = _get_stock_basic()
	l = len(stockList)
	lstMultiple = []
	print(time.ctime(),'-------- processing begin---------------')
	for i in range(l):
		if (not _should_skip(df, i, startDate)):
			hangqing = ts.pro_bar(ts_code=df.ts_code[i], adj='qfq', start_date=startDate, end_date=endDate)
			if hangqing is None:
				continue
			idx = len(hangqing)
			if (idx > 3):
				x = 0
				for j in range(idx-1):
					volChange = ( hangqing.vol[j] / hangqing.vol[j + 1] )
					if (volChange >= multiple and j > 2
					and hangqing.open[j]>hangqing.close[j+1]
					and hangqing.pct_chg[j]>4
					and ( hangqing.close[j-1]>hangqing.close[j] and -3 < hangqing.pct_chg[j-1]<3 and hangqing.vol[j] >= hangqing.vol[j-1]*multiple
					or hangqing.close[j-2]> hangqing.close[j] and -3 <hangqing.pct_chg[j-2]<3 and hangqing.vol[j] >= hangqing.vol[j-2]*multiple)
#or hangqing.change[j-2] < 3
					and hangqing.close[0] > hangqing.close[idx-1]):
						x = 1
						break
				if (x == 1):
					lstMultiple.append(df.ts_code[i])
					print(df.ts_code[i],j,hangqing.vol[j+1], hangqing.vol[j], round(volChange))
		if ( i % 100 == 99):
			print(time.ctime(), round(i/100)*100, ' records have been processed....')
		if ( i== l -1):
			print (time.ctime(), " All records have been processed!!!")
	print(time.ctime(),'-------- processing end-----------------')
	return lstMultiple

#获取向上跳空的股票，剔除科创版、ST和次新股
def getxiangshangtiaokongquekou(stockList='',startDate='',endDate=''):
	if(startDate is None or startDate == ''):
		print('startDate must input')
		return []
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d",time.localtime());print('endDate is ', endDate)
	if(stockList is None or stockList == ''):
		stockList = _default_stock_list()
	df = _get_stock_basic()
	l = len(stockList)
	lstMultiple = []
	print(time.ctime(),'-------- processing begin---------------')
	for i in range(l):
		if (not _should_skip(df, i, startDate)):
			hangqing = ts.pro_bar(ts_code=df.ts_code[i], adj='qfq', start_date=startDate, end_date=endDate)
			if hangqing is None:
				continue
			idx = len(hangqing)
			if (idx > 3):
				x = 0
				volChange = ( hangqing.vol[0] / hangqing.vol[1] )
				if (hangqing.low[0] > hangqing.high[1]
				and hangqing.close[0] > hangqing.close[idx-1]):
					x = 1
				if (x == 1):
					lstMultiple.append(df.ts_code[i])
					print(df.ts_code[i],hangqing.vol[1], hangqing.vol[0], round(volChange))
		if ( i % 100 == 99):
			print(time.ctime(), round(i/100)*100, ' records have been processed....')
		if ( i== l -1):
			print (time.ctime(), " All records have been processed!!!")
	print(time.ctime(),'-------- processing end-----------------')
	return lstMultiple

def getStockListByFluxRate(startDate='',endDate='',fluxRate='',filePath=''):
	if(startDate is None or startDate == ''):
		print('startDate must input')
		return
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d",time.localtime())
	if(fluxRate is None or fluxRate == ''):
		fluxRate = 50.00
	df = _get_stock_basic()
	stockList = df.ts_code
	l = len(stockList)
	fluxs={}
	print(time.ctime(),'-------- processing begin---------------')
	for i in range(l):
		if (not _should_skip(df, i)):
			hangqing = ts.pro_bar(ts_code=df.ts_code[i], adj='qfq', start_date=startDate, end_date=endDate)
			if (hangqing is not None):
				idx = len(hangqing)
				if (idx > 1):
					flux = ( hangqing.close[0] - hangqing.close[idx-1] ) / hangqing.close[idx-1] * 100
					flux2 = round(flux,2)
					if (flux2 >= fluxRate):
						fluxs[df.ts_code[i]] = flux2
		if ( i % 100 == 99):
			print(time.ctime(), round(i/100)*100, ' records have been processed....')
		if ( i== l -1):
			print (time.ctime(), " All records have been processed!!!")


	print(time.ctime(),'-------- processing ended---------------')
	flxs=sorted(fluxs.items(),key=lambda x:x[1],reverse = True)
	resultDf = DataFrame(flxs)
	resultDf.to_excel(filePath)

#选出曾经有过巨量上涨记录的股票，
def getStockListByVolumeChange(stockList='',startDate='',endDate='',multiple=''):
	if(startDate is None or startDate == ''):
		print('startDate must input')
		return []
	if(multiple is None or multiple == ''):
		print('multiple must input')
		return []
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d",time.localtime())
	if(stockList is None or stockList == ''):
		stockList = _default_stock_list()
	l = len(stockList)
	lstStocks=[]
	print(time.ctime(),'-------- processing begin---------------')
	for i in range(l):
#		if (df.symbol[i][0:3]!= '688' and df.name[i][0:2]!='ST' and df.name[i][0:2] !='*S' and df.list_date[i]<'20210101'
#		and df.list_date[i] < startDate):
		hangqing = ts.pro_bar(ts_code=stockList[i], adj='qfq', start_date=startDate, end_date=endDate)
		if(hangqing is not None):
			idx = len(hangqing)
			if (idx > 1):
				x = 0
				for j in range(idx-1):
					volChange = ( hangqing.vol[j] / hangqing.vol[j + 1] )
					if (volChange >= multiple and hangqing.open[j]>hangqing.close[j+1] and hangqing.change[j]>3
					and hangqing.close[0] > hangqing.close[idx-1]):
						x = 1
						break
				if (x == 1):
					lstStocks.append(stockList[i])
		# print(df.ts_code[i],j,hangqing.vol[j+1], hangqing.vol[j], round(volChange))
		if ( i % 100 == 99):
			print(time.ctime(), round(i/100)*100, ' records have been processed....')
		if ( i== l -1):
			print (time.ctime(), " All records have been processed!!!")
	return lstStocks

def getLiangzeng(stockList='',startDate='',endDate='',multiple=''):
	if(startDate is None or startDate == ''):
		print('startDate must input'); return []
	if(multiple is None or multiple == ''):
		print('multiple must input');return []
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d",time.localtime())
	if(stockList is None or stockList == ''):
		print('stockList must input');return []
	l = len(stockList)
	lstStocks=[]
	print(time.ctime(),'-------- processing begin---------------')
	for i in range(l):
		hangqing = ts.pro_bar(ts_code=stockList[i], adj='qfq', start_date=startDate, end_date=endDate)
		if(hangqing is not None):
			idx = len(hangqing)
			if (idx >= 9):
				x = 0
				for j in range(5):
					if(hangqing.vol[j + 1] > hangqing.vol[0] * multiple
					and (hangqing.vol[j + 1] > hangqing.vol[j+2] * 2.5 or hangqing.vol[j + 1] > hangqing.vol[j+3] * 2.5 or hangqing.vol[j + 1] > hangqing.vol[j+4] * 2.5)
					and hangqing.pct_chg [j+1] > 4
					and hangqing.close[0] > hangqing.close[idx-1]
					and hangqing.close[0] > hangqing.close[j+1]):
						x = 1; break
				if (x == 1):
					lstStocks.append(stockList[i])
		if ( i % 100 == 99):
			print(time.ctime(), round(i/100)*100, ' records have been processed....')
		if ( i== l -1):
			print (time.ctime(), " All records have been processed!!!")
	return lstStocks

#获取放量股票，当日放量倍数由multiple确定
def getFangliangDay0(stockList='',startDate='',endDate='',multiple=''):
	if(startDate is None or startDate == ''):
		print('startDate must input')
		return []
	if(multiple is None or multiple == ''):
		print('multiple must input')
		return []
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d",time.localtime())
	if(stockList is None or stockList == ''):
		stockList = _default_stock_list()
	l = len(stockList)
	lstMultiple = []
	print(time.ctime(),'-------- processing begin---------------')
	for i in range(l):
		hangqing = ts.pro_bar(ts_code=stockList[i], adj='qfq', start_date=startDate, end_date=endDate)
		if(hangqing is not None):
			idx = len(hangqing)
			if (idx > 1):
				if (hangqing.vol[0]> hangqing.vol[1] * multiple):
					lstMultiple.append(stockList[i])
		if ( i % 100 == 99):
			print(time.ctime(), round(i/100)*100, ' records have been processed....')
		if ( i== l -1):
			print (time.ctime(), " All records have been processed!!!")
	print(time.ctime(),'-------- processing end-----------------')
	return lstMultiple


#筛选区间内涨幅超过指定百分比的股票，排除科创板/ST/次新股
def getZhangFu(startDate='', endDate='', pct=30):
	if(startDate is None or startDate == ''):
		print('startDate must input')
		return []
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d", time.localtime())
	df = _get_stock_basic()
	stockList = df.ts_code
	l = len(stockList)
	lst = []
	print(time.ctime(), '-------- processing begin---------------')
	for i in range(l):
		if(not _should_skip(df, i, startDate)):
			hangqing = ts.pro_bar(ts_code=df.ts_code[i], adj='qfq', start_date=startDate, end_date=endDate)
			if hangqing is not None and len(hangqing) > 1:
				idx = len(hangqing)
				change = round((hangqing.close[0] - hangqing.close[idx-1]) / hangqing.close[idx-1] * 100, 2)
				if change >= pct:
					lst.append((df.ts_code[i], change))
					print(df.ts_code[i], f'{change}%')
		if(i % 100 == 99):
			print(time.ctime(), round(i/100)*100, ' records have been processed....')
		if(i == l - 1):
			print(time.ctime(), " All records have been processed!!!")
	print(time.ctime(), '-------- processing end-----------------')
	lst.sort(key=lambda x: x[1], reverse=True)
	return [item[0] for item in lst]


#6个点代表强势，相对于T-1或T-2日放量2倍以上且涨超6个点，寻找这样的股票。西藏珠峰7.2日启动，中泰股份20210826晚关注到

#获取Excel里的股票list，返回一个list出去
def getlistgupiao(file):
	if(file is None or file == ''):
		print('file must be input');return
	lista=[]
	wb=openpyxl.load_workbook(filename=file)
	sht=wb['Sheet1']
	for i in range(sht.max_row):
		lista.append(sht.cell(i+1,1).value)
	return lista


#========== 放量涨幅筛选（st_daily_signal）==========

#创建 st_daily 表（汇总所有个股日线数据）
def createDailyTable():
	mdb=_connect_sm()
	mycsr=mdb.cursor()
	sql="CREATE TABLE IF NOT EXISTS st_daily (" \
		"ts_code VARCHAR(12) NOT NULL," \
		"symbol VARCHAR(6) NOT NULL," \
		"trade_date VARCHAR(8) NOT NULL," \
		"openp FLOAT," \
		"high FLOAT," \
		"low FLOAT," \
		"closep FLOAT," \
		"pct_chg FLOAT," \
		"vol FLOAT," \
		"amount FLOAT," \
		"PRIMARY KEY (ts_code, trade_date)," \
		"INDEX idx_trade_date (trade_date)," \
		"INDEX idx_symbol (symbol)" \
		")"
	mycsr.execute(sql)
	mdb.commit()
	mycsr.close()
	mdb.close()
	print('st_daily table created')

#将所有 gp{symbol} 表的日线数据汇总到 st_daily 表
def buildDailyTable(startDate='', endDate=''):
	if(startDate is None or startDate == ''):
		startDate=(datetime.date.today()-datetime.timedelta(days=7)).strftime('%Y%m%d')
	if(endDate is None or endDate == ''):
		endDate=datetime.date.today().strftime('%Y%m%d')
	mdb=_connect_sm()
	mycsr=mdb.cursor()
	#获取 symbol → ts_code 映射
	sym2ts={}
	try:
		mycsr.execute("SELECT symbol, st_code FROM stocks")
		for row in mycsr.fetchall():
			sym2ts[row[0]]=row[1]
	except Exception:
		pass
	if not sym2ts:
		print('stocks表为空，从tushare API获取映射...')
		try:
			pro=ts.pro_api(TUSHARE_TOKEN)
			basic=pro.query('stock_basic',exchange='',list_status='L',fields='ts_code,symbol')
			for _,r in basic.iterrows():
				sym2ts[r['symbol']]=r['ts_code']
		except Exception as e:
			print('tushare API调用失败(%s)，使用规则映射...'%e)
	if not sym2ts:
		mycsr.execute("SHOW TABLES LIKE 'gp%%'")
		for (t,) in mycsr.fetchall():
			sym=t[2:]
			if(sym.startswith('6')):
				sym2ts[sym]=sym+'.SH'
			else:
				sym2ts[sym]=sym+'.SZ'
		print('已通过规则生成 %d 条 symbol→ts_code 映射'%len(sym2ts))
	mycsr.execute("SHOW TABLES LIKE 'gp%%'")
	tables=[t[0] for t in mycsr.fetchall()]
	total=len(tables)
	#预先计算日期范围内的已有记录，避免逐条查询
	sql_check="SELECT trade_date FROM st_daily WHERE ts_code=%s AND trade_date BETWEEN %s AND %s"
	sql_insert="INSERT IGNORE INTO st_daily(ts_code,symbol,trade_date,openp,high,low,closep,pct_chg,vol,amount) " \
		"VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
	print(time.ctime(),'-------- buildDailyTable begin (%d tables, %s~%s)---------------'%(total,startDate,endDate))
	count=0
	for k,table in enumerate(tables):
		sym=table[2:]
		ts_code=sym2ts.get(sym)
		if not ts_code:
			continue
		try:
			mycsr.execute("SELECT trade_date,openp,high,low,closep,pct_chg,vol,amount FROM `%s` WHERE trade_date BETWEEN %%s AND %%s"%(table),(startDate,endDate))
			rows=mycsr.fetchall()
			if not rows:
				continue
			#批量检查已有日期
			mycsr.execute(sql_check,(ts_code,startDate,endDate))
			existing=set(r[0] for r in mycsr.fetchall())
			vals=[]
			for row in rows:
				td=str(row[0])
				if td in existing:
					continue
				vals.append((ts_code,sym,td,row[1],row[2],row[3],row[4],row[5],row[6],row[7]))
			if vals:
				mycsr.executemany(sql_insert,vals)
				count+=len(vals)
				if(count%500==0):
					mdb.commit()
		except Exception as e:
			pass
		if(k%500==499):
			print(time.ctime(),round(k/500)*500,'tables processed,',count,'rows inserted')
	mdb.commit()
	mycsr.close()
	mdb.close()
	print(time.ctime(),'-------- buildDailyTable end: %d rows inserted---------------'%count)

#创建 st_daily_signal 表（放量涨幅信号表）
def createSignalTable():
	mdb=_connect_sm()
	mycsr=mdb.cursor()
	sql="CREATE TABLE IF NOT EXISTS st_daily_signal (" \
		"id INT AUTO_INCREMENT PRIMARY KEY," \
		"trade_date VARCHAR(8) NOT NULL," \
		"st_code VARCHAR(12) NOT NULL," \
		"closePrice FLOAT," \
		"pct_chg FLOAT," \
		"vol FLOAT," \
		"prev_vol FLOAT," \
		"vol_ratio FLOAT," \
		"created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP," \
		"UNIQUE KEY uk_date_code (trade_date, st_code)" \
		")"
	mycsr.execute(sql)
	mdb.commit()
	mycsr.close()
	mdb.close()
	print('st_daily_signal table created')

#筛选放量涨幅股票：当日成交量>=前日3倍且涨幅>6%，排除科创板/ST/次新股
#结果写入 st_daily_signal 表（去重插入）
def getLiangJiaFangLiang(startDate='', endDate=''):
	mdb=_connect_sm()
	mycsr=mdb.cursor()
	#获取st_daily中最近两个交易日
	if(endDate is None or endDate == ''):
		mycsr.execute("SELECT DISTINCT trade_date FROM st_daily ORDER BY trade_date DESC LIMIT 2")
		dates=mycsr.fetchall()
		if(len(dates)<2):
			print('st_daily数据不足两个交易日，请先运行buildDailyTable()')
			mycsr.close();mdb.close()
			return []
		today=dates[0][0]
		prev_day=dates[1][0]
	else:
		today=endDate
		mycsr.execute("SELECT DISTINCT trade_date FROM st_daily WHERE trade_date<%s ORDER BY trade_date DESC LIMIT 1",(today,))
		r=mycsr.fetchone()
		if not r:
			print('找不到前一交易日')
			mycsr.close();mdb.close()
			return []
		prev_day=r[0]
	#SQL联查：当日成交量>=前日3倍且涨幅>6%
	sql="SELECT a.ts_code,a.trade_date,a.closep,a.pct_chg,a.vol,b.vol AS prev_vol," \
		"ROUND(a.vol/b.vol,2) AS vol_ratio " \
		"FROM st_daily a JOIN st_daily b ON a.ts_code=b.ts_code " \
		"WHERE a.trade_date=%s AND b.trade_date=%s " \
		"AND a.vol>=b.vol*3 AND a.pct_chg>6"
	mycsr.execute(sql,(today,prev_day))
	rows=mycsr.fetchall()
	#加载stock_basic用于_should_skip过滤
	df=None
	ts_to_idx={}
	try:
		df=_get_stock_basic()
		ts_to_idx={df.ts_code[i]:i for i in range(len(df))}
	except Exception:
		pass
	result=[]
	for row in rows:
		ts_code=row[0]
		sym=ts_code.split('.')[0]
		#排除科创板(688)
		if(sym.startswith('688')):
			continue
		#如果有stock_basic数据，应用完整_should_skip过滤
		if df is not None:
			idx=ts_to_idx.get(ts_code)
			if idx is not None and _should_skip(df,idx):
				continue
		result.append({
			'st_code':row[0],'trade_date':row[1],'closePrice':row[2],
			'pct_chg':row[3],'vol':row[4],'prev_vol':row[5],'vol_ratio':row[6]
		})
	#写入st_daily_signal（去重插入）
	sql_insert="INSERT IGNORE INTO st_daily_signal(trade_date,st_code,closePrice,pct_chg,vol,prev_vol,vol_ratio) " \
		"VALUES(%s,%s,%s,%s,%s,%s,%s)"
	inserted=0
	for r in result:
		mycsr.execute(sql_insert,(r['trade_date'],r['st_code'],r['closePrice'],r['pct_chg'],r['vol'],r['prev_vol'],r['vol_ratio']))
		inserted+=mycsr.rowcount
	mdb.commit()
	mycsr.close()
	mdb.close()
	print(time.ctime(),'getLiangJiaFangLiang: %s vs %s, 筛选出%d只, 写入%d条新记录'%(today,prev_day,len(result),inserted))
	return result

