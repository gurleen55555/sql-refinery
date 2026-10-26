
from app.sql_runner import create_connection, execute_query

conn = create_connection()

query = """
SELECT
    c.country,
    COUNT(DISTINCT o.order_id) AS total_orders,
    ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.status = 'completed'
GROUP BY c.country
ORDER BY revenue DESC
"""

result = execute_query(conn, query)

print("Success:", result.ok)
print("Columns:", result.columns)
print("Rows:", result.rows)
print("Error:", result.error)

conn.close()
