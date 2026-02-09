# Copyright (C) 2019 Virta Laboratories, Inc.  All rights reserved.

"""Calculate beginning and end dates of quarters."""

import datetime


def quarter(dt):
    """Return the current quarter # of a datetime object as an integer [1..4].

    Jan, Feb, Mar: 1
    Apr, May, Jun: 2
    Jul, Aug, Sep: 3
    Oct, Nov, Dec: 4

    https://stackoverflow.com/a/1406182/3061818
    """
    return ((dt.month - 1) // 3) + 1


def quarter_start(dt):
    """Return datetime object for date/time of start of quarter."""
    q = quarter(dt)
    return datetime.datetime(year=dt.year,
                             month=(q * 3) - 2,
                             day=1,
                             tzinfo=dt.tzinfo)


def quarter_end(dt):
    """Return datetime object for date/time of end of quarter.

    Probably seems a little roundabout, but conceptually easy.

     - Find start of current quarter
     - Add 100 days, we'll be in next quarter (since there's at most 92
       days in a quarter)
     - Find the end of the "previous quarter of the next quarter."
    """
    date_in_next_quarter = quarter_start(dt) + datetime.timedelta(days=100)
    return prev_quarter_end(date_in_next_quarter)


def prev_quarter_start(dt):
    """Return datetime object for date/time of start of previous quarter."""
    return quarter_start(prev_quarter_end(dt))


def prev_quarter_end(dt):
    """Return datetime object for date/time of end of previous quarter."""
    curr_start = quarter_start(dt)
    prev_end = curr_start - datetime.timedelta(days=1)
    return prev_end.replace(hour=23, minute=59, second=59, microsecond=99999)
