import sys
import pymysql
sys.stdout.reconfigure(encoding='utf-8')

conn = pymysql.connect(host='localhost', user='root', password='P@ssw0rd', database='stockshare')
cursor = conn.cursor()

today = '20260927'
tasks = ['stock_basic', 'update_daily_data', 'run_strategies']

for task in tasks:
    cursor.execute(
        'INSERT INTO st_execution_status(task_name,exec_date,status) VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE exec_date=%s,status=%s',
        (task, today, 'Y', today, 'Y')
    )

conn.commit()
print(f'Updated status for {len(tasks)} tasks')

cursor.execute('SELECT task_name, exec_date, status FROM st_execution_status WHERE exec_date=%s', (today,))
rows = cursor.fetchall()
print(f'Recent records ({today}):')
for row in rows:
    print(f'  {row}')

conn.close()
