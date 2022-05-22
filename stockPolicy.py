import tushare as ts
import openpyxl
from pandas import DataFrame
import time
import mysql.connector
ts.set_token('4d47c02a8bb025881c9dd9e3c36d25139ab5b429a73353e566fc02a9')
pro = ts.pro_api()
df = pro.query('stock_basic')
stockList = df.ts_code
'stocks = stockList.array'
startDate = '20180104'
endDate   = '20181231'
valveRate = 50.00
filePath=r'C:\Users\Quan\Documents\stock\celue2018.xlsx'

#def myThread(threadName='', param=''):

def loadAllStockBasicsIntoMysql():
	pro = ts.pro_api('4d47c02a8bb025881c9dd9e3c36d25139ab5b429a73353e566fc02a9')
	df  = pro.query('stock_basic')
	stockList = df.ts_code
	l = len(stockList)
	mdb=mysql.connector.connect(host="localhost",user="root",passwd="1234",database='sm')
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
	return stockList

def loadALLStockDailyIntoMysqlAnyway(startDate='',endDate=''):
	if(startDate is None or startDate == ''):
		print('startDate must input')
		return
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d",time.localtime())
		print('end date is:',endDate)
	pro = ts.pro_api('4d47c02a8bb025881c9dd9e3c36d25139ab5b429a73353e566fc02a9')
	df  = pro.query('stock_basic')
	stockList = df.ts_code
	l = len(stockList)

	mdb=mysql.connector.connect(host="localhost",user="root",passwd="1234",database='sm')
	mycsr = mdb.cursor()
	sql = "delete from st_daily"
	sql2="insert into st_daily(trade_date,st_code,openPrice,highest,lowest,closePrice,pre_close,changedValue,pct_chg,vol,amount) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"

	print(time.ctime(),'-------- processing begin---------------')
	mycsr.execute(sql)
	mdb.commit()
	print(time.ctime(),'-------- table cleared ---------------')
#load daily transaction data
	for idx in range(l):
		hq = ts.pro_bar(ts_code=stockList[idx],adj='qfq',start_date=startDate,end_date=endDate)
		if (hq is not None):
			for i in range(len(hq)):
				trdate= hq.trade_date[i]
				stcode= hq.ts_code[i]
				openp = float(hq.open[i])
				closep= float(hq.close[i])
				precls= float(hq.pre_close[i])
				high  = float(hq.high[i])
				low   = float(hq.low[i])
				change= float(hq.change[i])
				pctchg= float(hq.pct_chg[i])
				vol   = float(hq.vol[i])
				amount= float(hq.amount[i])
				val2=(trdate,stcode,openp,high,low,closep,precls,change,pctchg,vol,amount)
				mycsr.execute(sql2,val2)
			mdb.commit()
		if ( idx % 100 == 99):
			print(time.ctime(), round(idx/100)*100, ' records have been processed....')
			time.sleep(5)     #睡眠5秒增加每百条记录处理时间，防止1分钟内调用pro_bar接口超过200次而报错
		if ( idx== l -1):
			print (time.ctime(), " All records have been processed!!!")
	print(time.ctime(),'-------- processing end-----------------')

def loadStockDailyIntoMysql(stockList='',startDate='',endDate=''):
	if(startDate is None or startDate == ''):
		print('startDate must input')
		return
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d",time.localtime())
		print('end date is:',endDate)
	if(len(stockList) == 0 or stockList == ''):
		pro = ts.pro_api('4d47c02a8bb025881c9dd9e3c36d25139ab5b429a73353e566fc02a9')
		df  = pro.query('stock_basic')
		stockList = df.ts_code
	l = len(stockList)

	mdb=mysql.connector.connect(host="localhost",user="root",passwd="1234",database='sm')
	mycsr = mdb.cursor()
	sql = "select * from st_daily where trade_date=%s and st_code=%s"
	sql2="insert into st_daily(trade_date,st_code,openPrice,highest,lowest,closePrice,pre_close,changedValue,pct_chg,vol,amount) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"

	print(time.ctime(),'-------- processing begin---------------')

#load daily transaction data
	for idx in range(l):
		hq = ts.pro_bar(ts_code=stockList[idx],adj='qfq',start_date=startDate,end_date=endDate)
		for i in range(len(hq)):
			val = (hq.trade_date[i],stockList[idx],)
			mycsr.execute(sql, val)
			result = mycsr.fetchall()
			if (len(result) == 0):
				trdate= hq.trade_date[i]
				stcode= hq.ts_code[i]
				openp = float(hq.open[i])
				closep= float(hq.close[i])
				precls= float(hq.pre_close[i])
				high  = float(hq.high[i])
				low   = float(hq.low[i])
				change= float(hq.change[i])
				pctchg= float(hq.pct_chg[i])
				vol   = float(hq.vol[i])
				amount= float(hq.amount[i])
				val2=(trdate,stcode,openp,high,low,closep,precls,change,pctchg,vol,amount)
				mycsr.execute(sql2,val2)
		mdb.commit()
		if ( idx % 100 == 99):
			print(time.ctime(), round(idx/100)*100, ' records have been processed....')
			time.sleep(5)     #睡眠5秒增加每百条记录处理时间，防止1分钟内调用pro_bar接口超过200次而报错
		if ( idx== l -1):
			print (time.ctime(), " All records have been processed!!!")
	print(time.ctime(),'-------- processing end-----------------')


#个股检测上涨动能算法：一个月内出现过单日6个点上涨的幅度(A日)。月底较月初上涨，A日过后振幅收窄且量缩（所有交易日的单日量没有一天超过A日总量），
#一个星期后可以买入，或等再一次涨幅超3个点时介入。

#选出迄今跳空过
def gettiaokongshangzhangguo(startDate='',endDate=''):
	if(startDate is None or startDate == ''):
		print('startDate must input')
		return
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d",time.localtime())
		print('end date is:',endDate)
	mdb=mysql.connector.connect(host="localhost",user="root",passwd="1234",database='sm')
	mycsr = mdb.cursor()
	sql = "select ts_code from st_basic"
	mycsr.execute(sql)
	stockList=mycsr.fetchall()
	l = len(stockList)
	lstMultiple = []
	print(time.ctime(),'-------- processing begin---------------')
	for i in range(l):
		if (df.symbol[i][0:3]!= '688' and df.name[i][0:2]!='ST' and df.name[i][0:2] !='*S' and df.list_date[i]<'20210101' 
		and df.list_date[i] < startDate):
			hangqing = ts.pro_bar(ts_code=df.ts_code[i], adj='qfq', start_date=startDate, end_date=endDate)
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
		return
	if(multiple is None or multiple == ''):
		multiple = 2;print('multiple is ', multiple)
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d",time.localtime())
	if(stockList is None or stockList == ''):
		pro = ts.pro_api('4d47c02a8bb025881c9dd9e3c36d25139ab5b429a73353e566fc02a9')
		df  = pro.query('stock_basic')
		stockList = df.ts_code
	l = len(stockList)
	lstMultiple = []
	print(time.ctime(),'-------- processing begin---------------')
	for i in range(l):
		if (df.symbol[i][0:3]!= '688' and df.name[i][0:2]!='ST' and df.name[i][0:2] !='*S' and df.list_date[i]<'20210101' 
		and df.list_date[i] < startDate):
			hangqing = ts.pro_bar(ts_code=df.ts_code[i], adj='qfq', start_date=startDate, end_date=endDate)
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
		return
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d",time.localtime());print('endDate is ', endDate)
	if(stockList is None or stockList == ''):
		pro = ts.pro_api('4d47c02a8bb025881c9dd9e3c36d25139ab5b429a73353e566fc02a9')
		df  = pro.query('stock_basic')
		stockList = df.ts_code
	l = len(stockList)
	lstMultiple = []
	print(time.ctime(),'-------- processing begin---------------')
	for i in range(l):
		if (df.symbol[i][0:3]!= '688' and df.name[i][0:2]!='ST' and df.name[i][0:2] !='*S' and df.list_date[i]<'20210101' 
		and df.list_date[i] < startDate):
			hangqing = ts.pro_bar(ts_code=df.ts_code[i], adj='qfq', start_date=startDate, end_date=endDate)
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
	l = len(stockList)
	fluxs={}
	print(time.ctime(),'-------- processing begin---------------')
	for i in range(l):
		if (df.symbol[i][0:3]!= '688' and df.name[i][0:2]!='ST' and df.name[i][0:2] !='*S' and df.list_date[i]<'20210101'):
			hangqing = ts.pro_bar(ts_code=df.ts_code[i], adj='qfq', start_date=startDate, end_date=endDate)
			if (hangqing is not None):
				idx = len(hangqing)
				if (idx > 1):
					flux = ( hangqing.close[0] - hangqing.close[idx-1] ) / hangqing.close[idx-1] * 100
					flux2 = round(flux,2)
					if (flux2 >= valveRate):
						fluxs[df.ts_code[i]] = flux2
		if ( i % 100 == 99):
			print(time.ctime(), round(i/100)*100, ' records have been processed....')
		if ( i== l -1):
			print (time.ctime(), " All records have been processed!!!")
					

	print(time.ctime(),'-------- processing ended---------------')
	flxs=sorted(fluxs.items(),key=lambda fluxs:fluxs[1],reverse = True)
	df = DataFrame(flxs)
	df.to_excel(filePath)

#选出曾经有过巨量上涨记录的股票，
def getStockListByVolumeChange(stockList='',startDate='',endDate='',multiple=''):
	if(startDate is None or startDate == ''):
		print('startDate must input')
		return
	if(multiple is None or multiple == ''):
		print('multiple must input')
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d",time.localtime())
	if(stockList is None or stockList == ''):
		pro = ts.pro_api('4d47c02a8bb025881c9dd9e3c36d25139ab5b429a73353e566fc02a9')
		df  = pro.query('stock_basic')
		stockList = df.ts_code
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
		print('startDate must input'); return
	if(multiple is None or multiple == ''):
		print('multiple must input');return
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d",time.localtime())
	if(stockList is None or stockList == ''):
		print('stockList must input');return
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

#获取上涨了multiple倍的股票,用访问数据库的方式替换之前的方法

def getFanbeigu(startDate='',endDate='',multiple=''):
	if(startDate is None or startDate == ''):
		print('startDate must be input')
		return
	if(multiple is None or multiple == ''):
		print('multiple must be input'); return
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d",time.localtime())

	mdb=mysql.connector.connect(host="localhost",user="root",passwd="1234",database='sm')
	mycsr = mdb.cursor()
	mycsr.execute("select * from st_basic")
	result = mycsr.fetchall()
	l = len(result)

	lstMultiple = []
	print(time.ctime(),'-------- processing begin---------------')
	for i in range(l):
		sql="select closePrice from st_daily where st_code =%s and trade_date in(%s,%s)"
		val =(result[i][0],startDate,endDate)
		mycsr.execute(sql,val)
		rst = mycsr.fetchall()
		if(len(rst) == 2 ):
			price1 = rst[1][0]
			price2 = rst[0][0]
			if (price2> price1 * multiple):
				lstMultiple.append(result[i][0])
				print(result[i][0],price1, price2)
		if ( i % 100 == 99):
			print(time.ctime(), round(i/100)*100, ' records have been processed....')
		if ( i== l -1):
			print (time.ctime(), " All records have been processed!!!")
	print(time.ctime(),'-------- processing end-----------------')
	return lstMultiple;

#获取放量股票，当日放量倍数由multiple确定
def getFangliangDay0(stockList='',startDate='',endDate='',multiple=''):
	if(startDate is None or startDate == ''):
		print('startDate must input')
		return
	if(multiple is None or multiple == ''):
		print('multiple must input')
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d",time.localtime())
	if(stockList is None or stockList == ''):
		pro = ts.pro_api('4d47c02a8bb025881c9dd9e3c36d25139ab5b429a73353e566fc02a9')
		df  = pro.query('stock_basic')
		stockList = df.ts_code
	l = len(stockList)
	lstMultiple = []
	print(time.ctime(),'-------- processing begin---------------')
	for i in range(l):
		hangqing = ts.pro_bar(ts_code=stockList[i], adj='qfq', start_date=startDate, end_date=endDate)
		if(hangqing is not None):
			idx = len(hangqing)
			if (idx > 1):
				if (hangqing.vol[0]> hangqing.vol[1] * multiple):
					lstMultiple.append(df.ts_code[i])
		if ( i % 100 == 99):
			print(time.ctime(), round(i/100)*100, ' records have been processed....')
		if ( i== l -1):
			print (time.ctime(), " All records have been processed!!!")
	print(time.ctime(),'-------- processing end-----------------')
	return lstMultiple;


def getStockListByVolumeChange(stockList='',startDate='',endDate='',multiple=''):
	if(startDate is None or startDate == ''):
		print('startDate must input')
		return
	if(multiple is None or multiple == ''):
		print('multiple must input')
	if(endDate is None or endDate == ''):
		endDate = time.strftime("%Y%m%d",time.localtime())
	if(stockList is None or stockList == ''):
		pro = ts.pro_api('4d47c02a8bb025881c9dd9e3c36d25139ab5b429a73353e566fc02a9')
		df  = pro.query('stock_basic')
		stockList = df.ts_code
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