from __future__ import annotations


def format_gcp_grid_count(virtual_rows, row_data) -> str:
    """Describe rows currently visible in the GCP grid.

    ``virtualRowData`` is Dash AG Grid's post-filter row collection. A None
    value means the grid has not yet published that collection, so the loaded
    rowData is used as the initial count. An empty list is a real zero-result
    filter and must not fall back to the unfiltered rows.
    """
    loaded_rows = list(row_data or [])
    visible_rows = loaded_rows if virtual_rows is None else list(virtual_rows or [])

    # A rowData refresh/delete can briefly race the grid's virtualRowData
    # update. Intersect on the stable GCP ID so a stale filtered snapshot never
    # counts records that are no longer present in the current dataset.
    current_ids = {
        str(row.get("gcp_id"))
        for row in loaded_rows
        if isinstance(row, dict) and row.get("gcp_id") not in (None, "")
    }
    visible_ids = [
        str(row.get("gcp_id"))
        for row in visible_rows
        if isinstance(row, dict) and row.get("gcp_id") not in (None, "")
    ]
    if len(current_ids) == len(loaded_rows) and len(visible_ids) == len(visible_rows):
        visible_count = sum(1 for item_id in visible_ids if item_id in current_ids)
    else:
        visible_count = len(visible_rows)

    loaded_count = len(loaded_rows)
    return f"Showing {visible_count:,} of {loaded_count:,} loaded GCP(s)."
