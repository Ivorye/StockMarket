import pymysql, pandas as pd, tushare as ts, loadStocks as ld

db=ld.connectDB()
df=ld.getStockBasic()
ld.createStockTable(df)
ld.loadAllBasic(df)
#将DF数据帧中从开始日期到结束日期之间的交易记录导入每支股票的数据库
ld.insertNewTransactonRecordForAllStocks(df,start_date='20240430',end_date='20240517')
