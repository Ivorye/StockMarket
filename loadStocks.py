import pymysql, pandas as pd, tushare as ts

#返回cursor.需要依赖本地已建立数据库schema（stockshare）
def connectDB():
	db=pymysql.connect(host='localhost',
		user='root',
		password='atos1234',
		database='stockshare')
	return db

#每天只能调用5次接口
def getStockBasic():
	pro = ts.pro_api("4d47c02a8bb025881c9dd9e3c36d25139ab5b429a73353e566fc02a9")
	data = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,fullname,area,industry,list_date')
	df=pd.DataFrame(data)
	return df

#获取stock_basic里面的股票列表，为每支股票创建历史记录表，注意open、close、change这三个是sql语法里的关键字，不能出现在sql中
def createStockTable(df=' '):
	l=len(df)
	db=connectDB()
	cursor=connectDB()
	for i in range (0,l):
		s="gp%s"%df.loc[i].symbol
		sql="""CREATE TABLE `stockshare`.`%s` (  `trade_date` VARCHAR(8) NOT NULL,`openp` FLOAT NOT NULL,`high` FLOAT NOT NULL,\
		`low` FLOAT NOT NULL,`closep` FLOAT NOT NULL,`preclose` FLOAT NOT NULL,`changes` FLOAT NOT NULL,`pct_chg` FLOAT NOT NULL,\
		`vol` FLOAT NOT NULL,`amount` FLOAT NOT NULL,PRIMARY KEY (`trade_date`),UNIQUE INDEX `trade_date_UNIQUE` (`trade_date` ASC) VISIBLE);""" %(s)
		try:
			cursor.execute(sql)
			x = i%50
			if x == 0:
				print(i, " tables have been created")
			if i==l-1:
				print(i, " All tables have been created")
		except:
			print("exception throw")


#将所有股票基本信息载入总表
def loadAllBasic(df=' '):
	l=len(df)
	db=connectDB()
	cursor=connectDB()
	for i in range (0,l):
		symbol=df.loc[i].symbol
		sql0="select count(*) from stocks where symbol=%s" %symbol
		sql="insert into stocks(id,symbol,st_code,fullname,list_date) values('%s','%s','%s','%s','%s')" %(i+1,df.loc[i].symbol,df.loc[i].ts_code,df.loc[i].fullname,df.loc[i].list_date)
		quantity = cursor.execute(sql0)
		if quantity == 0:
			try:
				cursor.execute(sql)
				x = i%50
				if x == 0:
					db.commit()
					print(i, " records have been loaded to database")
				if i==l-1:
					db.commit()
					print(i, "All records have been loaded to database")
			except:
				print("exception throw")
				db.rollback()
	db.close()

#pro = ts.pro_api("4d47c02a8bb025881c9dd9e3c36d25139ab5b429a73353e566fc02a9")
#b
#for k in range(0,l):
	# data=pro.daily(ts_code=df.loc[k].ts_code,start_date='20230104',end_date='20240308')
	# s="gp%s"%df.loc[k].symbol
#输入：DF数据帧，开始日期和结束日期。在此之间的交易记录导入数据库
def insertNewTransactonRecordForAllStocks(df='',start_date='',end_date=''):
	l=len(df)
	db=connectDB()
	cursor = db.cursor()
	pro = ts.pro_api("4d47c02a8bb025881c9dd9e3c36d25139ab5b429a73353e566fc02a9")
	for k in range(0,l):
		data=pro.daily(ts_code=df.loc[k].ts_code,start_date=start_date,end_date=end_date)
		table="gp%s"%df.loc[k].symbol
		ln=len(data)
		for i in range(0,ln):
			sql0="select trade_date from %s where trade_date =%s" %(table,data.loc[i].trade_date)
			sql="insert into %s(trade_date,openp,high,low,closep,preclose,changes,pct_chg,vol,amount) values('%s','%s','%s','%s','%s','%s','%s','%s','%s','%s')" %(table,data.loc[i].trade_date,data.loc[i].open,data.loc[i].high,data.loc[i].low,data.loc[i].close,data.loc[i].pre_close,data.loc[i].change,data.loc[i].pct_chg,data.loc[i].vol,data.loc[i].amount)
			result=cursor.execute(sql0)
			if result==0:
				try:
					cursor.execute(sql)
					x = i%50
					if x == 0:
						db.commit()
						print(i, " records have been loaded to database")
					if i==ln-1:
						db.commit()
						print(i, "All records have been loaded to database")
				except:
					print("exception throw")
					db.rollback()
		kk=k%50
		if kk == 0:
			print(kk, " tables have been processed")
		if k == l-1:
			print(kk, " All tables have been processed")

	db.close()


#获取给定日期段内阶段涨幅大于rate的股票，返回一个股票列表list
def getJDZF(df='',start_date='',end_date='',rate=''):
	l=len(df)
	lst=[]
	for i in range(0,l):
		symbol=df.loc[i].symbol
		table="gp%s"%symbol
		sql="select closep from %s where trade_date = %s;" %(table,start_date)
		sql2="select closep from %s where trade_date = %s;" %(table,end_date)
		try:
			cursor.execute(sql)
			p1 = cursor.fetchall()
			cursor.execute(sql2)
			p2 = cursor.fetchall()
			p3 = p1[0][0]
			p4 = p2[0][0]
			ratio=1+rate/100
			if p4>p3*ratio:
				lst.append(symbol)
			x = i%500
			if x == 0:
				print(i, " records processed")
			if i==l-1:
				print(i, "All records processed")
		except:
			print("exception throw")
	return lst