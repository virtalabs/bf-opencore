
'''
Client for ODBC SQL connections.

To use this client, inherit from it and override the get_num_assets() and
get_page() functions.

EXAMPLE:
class MyClient(connectors.utils.MSSQLClient):
    def get_num_assets(self):
        return self.query_value("""
            SELECT COUNT(myId)
            FROM myTable
            WHERE myStatus = 'active'
            """)

    def get_page(self, size, offset):
        self.validate_columns(self.columns_str.split(","))
        return self.query_dict(
            """
            SELECT {columns_str}
            FROM myTable
            WHERE myStatus = 'active'
            ORDER BY myId
            OFFSET ? ROWS
            FETCH NEXT ? ROWS ONLY
            """.format(columns_str=self.columns_str),
            (offset, size),
        )
'''
from abc import ABC, abstractmethod
import tempfile
import math
import re
from collections import OrderedDict
import csv
import celery
import pyodbc
from blueflow.exceptions import ConnectorTaskError

logger = celery.utils.log.get_task_logger(__name__)


class MSSQLClient(ABC):
    """
    Client for a Microsoft SQL Server backend.

    Queries take a while, so we use SQL pagination and append to a CSV
    file.  After all rows have been retrieved, read the file and return it.
    """

    def __init__(self, server, port, database, username, password,
                 columns='*', pagination_size=1000):
        """
        Initialize SQL client with necessary credentials.

        The columns field is a list of column names.  All other columns will
        be ignored.  The default is all columns.
        """
        # pylint: disable=super-init-not-called
        # We really do need all this information to connect to the database.
        # pylint: disable=too-many-arguments
        self.pagination_size = pagination_size
        if port is None or port == "":
            # Some TMS instances don't like port number
            self.connstr = (
                'DRIVER=FreeTDS;'
                'SERVER={};'
                'DATABASE={};'
                'UID={};'
                'PWD={}'
            ).format(server, database, username, password)
        else:
            # Some TMS instances REQUIRE the port number
            self.connstr = (
                'DRIVER=FreeTDS;'
                'SERVER={};'
                'PORT={};'
                'DATABASE={};'
                'UID={};'
                'PWD={}'
            ).format(server, port, database, username, password)
        logger.debug("Connection string is %s", self.connstr)

        # Validate column names and parse list of column names into a
        # comma-separated list of strings appropriate for a SELECT query.
        self.validate_columns(columns)
        self.columns_str = '*' if columns == '*' else ','.join(columns)

        # Make sure we can connect
        try:
            conn = pyodbc.connect(self.connstr)
        except pyodbc.Error as err:
            logger.debug(err)
            raise ConnectorTaskError("Error connecting to database.")
        else:
            conn.close()

        # Temporary filename
        dummy, filename = tempfile.mkstemp(suffix='.csv')
        logger.debug("Will write rows to %s", filename)

    @abstractmethod
    def get_num_assets(self):
        """Return number of assets in the database."""

    @abstractmethod
    def get_page(self, size, offset):
        """Return one page of assets from the database as a list-of-dict.

        Return an empty list if there are no rows.  Each list item is one row.
        Each row is a dict keyed on column name.  Consider using the
        query_dict() helper function to implement get_page().
        """

    @staticmethod
    def validate_columns(columns):
        """Validate column names to avoid SQL injection.

        Raise ConnectorTaskError for non-alphanumeric names.

        Implemented as a static method so that it can be used later by a
        connector for fail-fast behavior.

        We can't simply use pydobc's '?' notation because the column names are
        part of the query (as opposed to the data in the query).  The column
        names need to be flexible because the user will provide them via a
        FieldMap, mapping BlueFlow ORM field names to column names in the
        MS SQL database.
        """
        # Special case for "all columns"
        if len(columns) == 1 and columns[0] == '*':
            return None

        # Each column name is alphanumeric
        for name in columns:
            if not re.match(r"^[A-Za-z0-9_]+$", name):
                raise ConnectorTaskError(
                    "Column name '{}' is not alphanumeric.".format(name)
                )
        return None

    def get_server_version(self):
        """Return version of the database server software."""
        return self.query_value("SELECT @@VERSION")

    def get_num_pages(self):
        """
        Return number of pages required to retrieve all data.

        One SQL query returns on page.
        """
        nassets = self.get_num_assets()
        return math.ceil(nassets / self.pagination_size)

    def get_all_pages_csv(self, increment_progress_callback=lambda: None):
        """
        Query database in pages, writing out to CSV and returning the filename.

        The caller is responsible for deleting returned temp file.

        If increment_progress_callback is specified, call it after
        each page.  The total number of calls will be get_num_pages().
        """
        dummy, csvfilename = tempfile.mkstemp(suffix='.csv')
        logger.debug("Created temporary file %s", csvfilename)
        increment_progress_callback()

        # Write CSV rows
        logger.debug("Writing %s", csvfilename)
        offset = 0
        while True:
            logger.debug("Retrieving %s assets at offset %s",
                         self.pagination_size, offset)

            # Query
            rows = self.get_page(size=self.pagination_size, offset=offset)

            # Stop if no more rows remain
            if not rows:
                break

            # Write CSV header on the first iteration
            if offset == 0:
                with open(csvfilename, 'w') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=rows[0].keys())
                    writer.writeheader()

            # Append rows to file
            with open(csvfilename, 'a') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=rows[0].keys())
                for row in rows:
                    writer.writerow(row)

            # Increment by self.pagination_size
            offset += self.pagination_size

        # Return temp filename to the caller
        return csvfilename

    def query_value(self, query):
        """Execute SQL query and return a single value.

        Return None if there is no such value.
        """
        try:
            conn = pyodbc.connect(self.connstr)
            cur = conn.cursor()
            cur.execute(query)
            value = cur.fetchone()[0]
            return value
        except pyodbc.Error as err:
            raise ConnectorTaskError(
                'Error: failed to execute SQL query: {}'''.format(err))
        except TypeError:
            # fetchone() returns None if there are no rows, so fetchone()[0]
            # will yield TypeError.
            return None
        finally:
            conn.close()

    def query_dict(self, query, *params):
        """Execute SQL query and return a list-of-dict keyed on column name."""
        try:
            conn = pyodbc.connect(self.connstr)
            cur = conn.cursor()
            cur.execute(query, *params)
            dbrows = cur.fetchall()
        except pyodbc.Error as err:
            raise ConnectorTaskError(
                'Error: failed to execute SQL query: {}'.format(err))
        finally:
            conn.close()

        # Convert database rows to list-of-dict
        fieldnames = [column[0] for column in cur.description]
        rows = []
        for dbrow in dbrows:
            row = OrderedDict(zip(fieldnames, dbrow))
            rows.append(row)
        return rows
