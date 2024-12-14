import sqlite3


def exec_sql_command(db_file, sql_cmd):
    """
    Executes a SQL command and returns output
    :param db_file: Directory path to the SQL Database
    :type db_file: str
    :param sql_cmd: SQL command to send
    :type sql_cmd: str
    """
    connection = sqlite3.connect(db_file)
    crsr = connection.cursor()
    crsr.execute(sql_cmd)
    output = crsr.fetchall()
    connection.close()
    return output


def fetch_sql_table(db_file, table_name, column_lst=None):
    """
    Fetches a table from a database -- with only specified columns if column_lst is specified
    Returns to a dictionary
    """

    # Building SQL Command to select items
    sql_cmd = 'SELECT '
    if column_lst is not None:
        counter = 0
        for column in column_lst:
            sql_cmd += column
            if counter + 1 < len(column_lst):
                sql_cmd += ', '
            counter += 1
    else:
        sql_cmd += '*'
    sql_cmd += ' from {};'.format(table_name)

    row_lst = exec_sql_command(db_file, sql_cmd)

    table_dict_lst = []

    row_number = 1
    for row in row_lst:
        row_dict = {}
        row_dict['row_number'] = row_number
        current_column = 0
        for column in column_lst:
            row_dict[column] = row[current_column]
            current_column += 1
        table_dict_lst.append(row_dict)
        row_number += 1

    return table_dict_lst
