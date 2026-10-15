"""Bound worksheet reads by values, excluding formatting-only Excel cells."""


def value_bounds(worksheet):
    # Normal-mode openpyxl retains sparse cells. Avoid iter_rows() over its
    # max_column/max_row: a formatted final column can create millions of cells.
    rows = columns = 0
    for cell in worksheet._cells.values():
        if cell.value is not None:
            rows = max(rows, cell.row)
            columns = max(columns, cell.column)
    return rows, columns


def value_rows(worksheet):
    rows, columns = value_bounds(worksheet)
    if not rows or not columns:
        return []
    return list(worksheet.iter_rows(min_row=1, max_row=rows,
                                    min_col=1, max_col=columns, values_only=True))
