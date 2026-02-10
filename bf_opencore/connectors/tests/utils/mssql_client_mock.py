"""Utilities for creating a mock MSSQL Client."""

import tempfile
import csv


def write_temp_csv(data, fieldnames):
    """
    Write a temporary file that mimics one downloaded by MSSQLClient.

    INPUTS
    - data is a list-of-dict keyed on fieldnames
    - fieldnames is a list of columns names for the CSV header row
    """
    csvfd, csvfilename = tempfile.mkstemp(suffix='.csv')
    with open(csvfd, 'w') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)
    return csvfilename


def configure_mock_mssqlclient(mock_mssqlclient, data, fieldnames):
    """Write csvtext to file and configure mock mssqlclient to return it."""
    # Mock connection function.  It won't actually try to connect.
    mock_mssqlclient.connect.return_value = None

    # Mock get_server_version() return value
    mock_mssqlclient.return_value.\
        get_server_version.return_value = "Version 14"

    # Mock get_num_pages() return value, assumes pagination size = 1000
    assert len(data) <= 1000, "Assuming pagination size == 1000"
    mock_mssqlclient.return_value.\
        get_num_pages.return_value = 1

    # Mock get_num_assets() return value
    mock_mssqlclient.return_value.\
        get_num_assets.return_value = len(data)

    # Write data to a temp file
    csvfilename = write_temp_csv(data, fieldnames)

    # Mock get_all_pages_csv() to return the temp filename
    mock_mssqlclient.return_value.\
        get_all_pages_csv.return_value = csvfilename
