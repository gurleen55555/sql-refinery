from app.llm import suggest_sql_rewrite

original_sql = """
SELECT country, COUNT(*) AS customer_count
FROM customers
GROUP BY country
ORDER BY customer_count DESC
"""

result = suggest_sql_rewrite(original_sql)

print("Success:", result.ok)
print("Model:", result.model)
print("Original SQL:", original_sql)
print("Optimized SQL:", result.optimized_sql)
print("Rationale:", result.rationale)
print("Error:", result.error)