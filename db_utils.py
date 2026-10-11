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


def update_execution_status(task_name, status='Y', exec_date=None, driver='pymysql', source='system'):
    """
    更新任务执行状态
    
    Args:
        task_name: 任务名称
        status: 状态值，默认为 'Y'
        exec_date: 执行日期（YYYYMMDD格式），默认为当天
        driver: 数据库驱动类型 ('pymysql' 或 'mysql.connector')
        source: 更新来源，'manual'=人工，'system'=系统自动（默认）
    """
    try:
        if exec_date is None:
            exec_date = datetime.date.today().strftime('%Y%m%d')
        if source not in ('manual', 'system'):
            source = 'system'
        
        if driver == 'pymysql':
            db = connect_pymysql()
        else:  # mysql.connector
            db = connect_mysql_connector()
        
        cursor = db.cursor()
        sql = (
            "INSERT INTO st_execution_status(task_name,exec_date,source,status) "
            "VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE exec_date=%s,source=%s,status=%s"
        )
        cursor.execute(sql, (task_name, exec_date, source, status, exec_date, source, status))
        db.commit()
        cursor.close()
        db.close()
    except Exception as e:
        print(f'更新执行状态失败: {e}')


def escape_table_name(name):
    """用反引号包裹表名，防止SQL关键字冲突"""
    return f"`{name.replace('`', '')}`"


def ensure_execution_status_table(driver='pymysql'):
    """确保 st_execution_status 表存在，且 status 前有 source 字段（人工=manual，系统=system）。"""
    try:
        db = connect_pymysql() if driver == 'pymysql' else connect_mysql_connector()
        cursor = db.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS st_execution_status ("
            "  task_name VARCHAR(50) NOT NULL PRIMARY KEY,"
            "  exec_date VARCHAR(8),"
            "  source VARCHAR(10) DEFAULT 'system' COMMENT '更新来源：manual=人工，system=系统自动',"
            "  status VARCHAR(1) DEFAULT 'N'"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        )
        # 兼容旧表：status 前缺 source 字段时补上
        cursor.execute("SHOW COLUMNS FROM st_execution_status LIKE 'source'")
        if not cursor.fetchone():
            cursor.execute(
                "ALTER TABLE st_execution_status "
                "ADD COLUMN source VARCHAR(10) DEFAULT 'system' "
                "COMMENT '更新来源：manual=人工，system=系统自动' AFTER exec_date"
            )
        db.commit()
        cursor.close()
        db.close()
    except Exception as e:
        print(f'确保 st_execution_status 表失败: {e}')
