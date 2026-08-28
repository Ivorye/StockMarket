import loadStocks as ld
import stockPolicy as sp

db=ld.connectDB()
df=ld.getStockBasic()
ld.createStockTable(df)
ld.loadAllBasic(df)
#将DF数据帧中从开始日期到结束日期之间的交易记录导入统一的 st_daily 表
ld.insertNewTransactonRecordForAllStocks(df,start_date='20260730',end_date='20260822')

#放量涨幅筛选：汇总日线数据到st_daily，筛选成交量>=前日3倍且涨幅>6%的股票
sp.createDailyTable()
sp.createSignalTable()
sp.buildDailyTable(startDate='20260730',endDate='20260822')
result=sp.getLiangJiaFangLiang()
print('放量涨幅筛选结果:',result)
