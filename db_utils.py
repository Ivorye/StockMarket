"""
数据库工具模块
提供通用的数据库连接和执行状态管理功能
"""
import datetime
import pymysql
import mysql.connector


def connect_pymysql():
    """使用 pymysql 连接数据库 (loadStocks.py, main.py 使用)"""
    return pymysql.connect(
        host='localhost',
        user='root',
        password='P@ssw0rd',
        database='stockshare',
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30
    )


def connect_mysql_connector():
    """使用 mysql.connector 连接数据库 (stockPolicy.py 使用)"""
    return mysql.connector.connect(
        host="localhost",
        user="root",
        passwd="P@ssw0rd",
        database='stockshare',
        connection_timeout=10
    )


def check_execution_status(task_name, exec_date=None, driver='pymysql'):
    """
    检查任务是否已成功执行过
    
    Args:
        task_name: 任务名称
        exec_date: 执行日期（YYYYMMDD格式），默认为当天
        driver: 数据库驱动类型 ('pymysql' 或 'mysql.connector')
    
    Returns:
        bool: 任务是否已成功执行
    """
    try:
        if exec_date is None:
            exec_date = datetime.date.today().strftime('%Y%m%d')
        
        if driver == 'pymysql':
            db = connect_pymysql()
        else:  # mysql.connector
            db = connect_mysql_connector()
        
        cursor = db.cursor()
        cursor.execute(
            "SELECT status FROM st_execution_status WHERE task_name=%s AND exec_date=%s",
            (task_name, exec_date)
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()
        return row and row[0] == 'Y'
    except Exception:
        return False


def update_execution_status(task_name, status='Y', exec_date=None, driver='pymysql'):
    """
    更新任务执行状态
    
    Args:
        task_name: 任务名称
        status: 状态值，默认为 'Y'
        exec_date: 执行日期（YYYYMMDD格式），默认为当天
        driver: 数据库驱动类型 ('pymysql' 或 'mysql.connector')
    """
    try:
        if exec_date is None:
            exec_date = datetime.date.today().strftime('%Y%m%d')
        
        if driver == 'pymysql':
            db = connect_pymysql()
        else:  # mysql.connector
            db = connect_mysql_connector()
        
        cursor = db.cursor()
        sql = (
            "INSERT INTO st_execution_status(task_name,exec_date,status) "
            "VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE exec_date=%s,status=%s"
        )
        cursor.execute(sql, (task_name, exec_date, status, exec_date, status))
        db.commit()
        cursor.close()
        db.close()
    except Exception as e:
        print(f'更新执行状态失败: {e}')


def escape_table_name(name):
    """用反引号包裹表名，防止SQL关键字冲突"""
    return f"`{name.replace('`', '')}`"