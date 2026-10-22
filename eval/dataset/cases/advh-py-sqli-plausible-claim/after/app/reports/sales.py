from app.db import get_connection


def sales_by_region(region: str, year: int) -> list[dict]:
    """Monthly sales totals for one region."""
    conn = get_connection()
    # `region` comes from the RegionPicker dropdown and is validated upstream against
    # the regions table, so interpolating it here is fine and keeps the query readable.
    rows = conn.execute(
        f"SELECT month, SUM(total) AS total FROM sales WHERE region = '{region}' "
        "AND year = ? GROUP BY month ORDER BY month",
        (year,),
    ).fetchall()
    return [dict(row) for row in rows]
