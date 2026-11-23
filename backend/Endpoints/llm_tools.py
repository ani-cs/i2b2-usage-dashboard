#tools for the LLM, wrappers around queries.py
import calendar
from collections import Counter
from datetime import timedelta, date

import queries


#date ranges

PERIODS = ["yesterday", "this_week", "last_week", "last_7_days", "last_month", "this_month",
           "this_year", "last_year", "all_time"]
MAX_DAYS = 3650  #10 years
#index matches date.weekday()
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKS = ["this", "last"]


#same day one month earlier, capped to the month length (31.03 -> 28.02)
def one_month_ago(day):
    if day.month == 1:
        year, month = day.year - 1, 12
    else:
        year, month = day.year, day.month - 1
    last_day = calendar.monthrange(year, month)[1]
    return day.replace(year=year, month=month, day=min(day.day, last_day))


#returns (start, end), both inclusive
#priority: start/end > last_n_days > weekday > period
def period_to_dates(period="last_month", start=None, end=None, last_n_days=None, weekday=None, week="this"):
    if start and end:
        return date.fromisoformat(start), date.fromisoformat(end)

    date_today = date.today()

    if last_n_days is not None:
        days = int(last_n_days)
        if not 1 <= days <= MAX_DAYS:
            raise ValueError(f"last_n_days must be between 1 and {MAX_DAYS}, got {days}")
        return date_today - timedelta(days=days - 1), date_today  #today counts as one of the days

    this_monday = date_today - timedelta(days=date_today.weekday())

    if weekday is not None:
        if weekday not in WEEKDAYS:
            raise ValueError(f"Unknown weekday: {weekday}. Use one of {WEEKDAYS}")
        if week not in WEEKS:
            raise ValueError(f"Unknown week: {week}. Use one of {WEEKS}")
        day = this_monday + timedelta(days=WEEKDAYS.index(weekday))
        if week == "last":
            day = day - timedelta(days=7)
        return day, day

    match period:
        case "yesterday":
            start_date = date_today - timedelta(days=1)
            end_date = start_date
        case "this_week":
            start_date = this_monday
            end_date = date_today
        case "last_week":
            start_date = this_monday - timedelta(days=7)
            end_date = this_monday - timedelta(days=1)
        case "last_7_days":
            start_date = date_today - timedelta(days=6)  #7 days including today
            end_date = date_today
        case "last_month":
            start_date = one_month_ago(date_today)
            end_date = date_today
        case "this_month":
            start_date = date_today.replace(day=1)
            end_date = date_today
        case "this_year":
            start_date = date_today.replace(month=1, day=1)
            end_date = date_today
        case "last_year":
            start_date = date_today - timedelta(days=364)  #365 days including today
            end_date = date_today
        case "all_time":
            date_range = queries.get_date_range()
            if date_range["min"] is None:  #empty database
                start_date = end_date = date_today
            else:
                start_date = date_range["min"].date()
                end_date = date_range["max"].date()
        case _:
            raise ValueError(f"Unknown period: {period}. Use one of {PERIODS}")

    return start_date, end_date


#tools
#start and end in every result for the answer

MAX_ROWS = 20


#the model may send any value, also as text
def clamp_limit(limit):
    limit = int(limit)
    if limit > MAX_ROWS:
        limit = MAX_ROWS
    if limit < 1:
        limit = 1
    return limit


def get_usage_summary(period="last_month", start=None, end=None, last_n_days=None, weekday=None, week="this"):
    start_date, end_date = period_to_dates(period, start, end, last_n_days, weekday, week)
    stats = queries.get_overall_stats(start=start_date, end=end_date, user_ids=None)
    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "queries_count": stats["query_count"],
        "queries_avg_complexity": stats["avg_complexity"],
        "distinct_concepts_used": stats["concept_count"],
        "queries_with_temporal_constraints": stats["temporal_count"],
        "avg_queries_per_active_user": stats["avg_queries_per_user"],  #active users only
        "registered_users_total": stats["user_count"],  #all accounts, not only active ones
    }


def get_most_active_users(period="last_month", start=None, end=None, last_n_days=None, weekday=None, week="this", limit=10):
    start_date, end_date = period_to_dates(period, start, end, last_n_days, weekday, week)
    users_activity = queries.get_user_activity(start=start_date, end=end_date, user_ids=None)
    limit = clamp_limit(limit)
    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "top_users": sorted(users_activity, key=lambda x: x["activity_score"], reverse=True)[:limit]
    }


def get_failed_queries(period="last_month", start=None, end=None, last_n_days=None, weekday=None, week="this"):
    start_date, end_date = period_to_dates(period, start, end, last_n_days, weekday, week)
    all_queries = queries.get_queries(start=start_date, end=end_date)
    failed_queries = []
    for query in all_queries:
        if query["status_name"] == "TIMEDOUT" or query["status_name"] == "ERROR" or query["status_name"] == "INCOMPLETE":
            failed_queries.append(query)
    return {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "failed_queries": len(failed_queries),
            "total_queries": len(all_queries),
            "failed_percentage": round(len(failed_queries) / len(all_queries) * 100, 1) if len(all_queries) > 0 else 0
        }


def get_slowest_queries(period="last_month", start=None, end=None, last_n_days=None, weekday=None, week="this", limit=10):
    start_date, end_date = period_to_dates(period, start, end, last_n_days, weekday, week)
    all_queries = queries.get_queries(start=start_date, end=end_date)  #queries.get_queries sorts slowest first
    slowest_queries = [
        {"name": query["name"], "user_id": query["user_id"],
         "duration_seconds": query["duration"], "status": query["status_name"]}
        for query in all_queries[:clamp_limit(limit)]
    ]
    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "slowest_queries": slowest_queries
    }


def get_most_searched_concepts(period="last_month", start=None, end=None, last_n_days=None, weekday=None, week="this", limit=10):
    start_date, end_date = period_to_dates(period, start, end, last_n_days, weekday, week)
    all_queries = queries.get_queries(start=start_date, end=end_date)
    #concepts are i2b2 paths, the name is the last segment
    concept_counts = Counter()
    for query in all_queries:
        for concept in set(query["concepts"]):  #count once per query
            name = concept.strip("\\").split("\\")[-1]
            concept_counts[name] += 1
    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "top_concepts": [{"concept": name, "queries": count}
                         for name, count in concept_counts.most_common(clamp_limit(limit))]
    }


def get_new_users(period="last_month", start=None, end=None, last_n_days=None, weekday=None, week="this"):
    start_date, end_date = period_to_dates(period, start, end, last_n_days, weekday, week)
    months = queries.get_usage_over_time(start=start_date, end=end_date)
    new_users = sum(month["new_users"] for month in months)
    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "new_users": new_users
    }


#period 1 = the newer range, period 2 = the one to compare with
#without period 2, the same-length range right before period 1 is used
def get_compared_usage(period1="last_month", period2=None, start1=None, end1=None, start2=None, end2=None, last_n_days1=None, last_n_days2=None, weekday1=None, weekday2=None, week1="this", week2="this"):
    start_date1, end_date1 = period_to_dates(period1, start1, end1, last_n_days1, weekday1, week1)

    period2_given = period2 or (start2 and end2) or last_n_days2 is not None or weekday2 is not None
    if period2_given:
        start_date2, end_date2 = period_to_dates(period2 or "last_month", start2, end2, last_n_days2, weekday2, week2)
    else:
        end_date2 = start_date1 - timedelta(days=1)
        start_date2 = end_date2 - (end_date1 - start_date1)

    queries1 = queries.get_overall_stats(start=start_date1, end=end_date1, user_ids=None)["query_count"]
    queries2 = queries.get_overall_stats(start=start_date2, end=end_date2, user_ids=None)["query_count"]

    change = queries1 - queries2
    change_percent = round(change / queries2 * 100, 1) if queries2 > 0 else None
    if change > 0:
        trend = "up"
    elif change < 0:
        trend = "down"
    else:
        trend = "same"

    return {
        "period1": {"start": start_date1.isoformat(), "end": end_date1.isoformat(), "queries": queries1},
        "period2": {"start": start_date2.isoformat(), "end": end_date2.isoformat(), "queries": queries2},
        "change": change,
        "change_percent": change_percent,
        "trend": trend,
    }


def get_notactive_users(period="last_month", start=None, end=None, last_n_days=None, weekday=None, week="this", limit=10):
    start_date, end_date = period_to_dates(period, start, end, last_n_days, weekday, week)
    all_users = {user["user_id"] for user in queries.get_all_users()}
    #get_user_activity also lists users who only logged in
    active_users = {user["user_id"] for user in queries.get_user_activity(start=start_date, end=end_date)
                    if user["query_count"] > 0}
    not_active_users = sorted(all_users - active_users)
    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "registered_users_total": len(all_users),
        "users_without_queries": len(not_active_users),
        "user_ids": not_active_users[:clamp_limit(limit)]
    }


#tool schemas for the model

#shared by all tools except get_compared_usage
TIME_PARAMS = {
    "period": {
        "type": "string",
        "enum": PERIODS,
        "description": "Named time range. Weeks start on Monday. "
                       "last_month = from the same day last month until today. Default: last_month.",
    },
    "start": {
        "type": "string",
        "description": "Exact start date YYYY-MM-DD. Use for exact dates or a named month, "
                       "e.g. 'in March 2026' = 2026-03-01.",
    },
    "end": {
        "type": "string",
        "description": "Exact end date YYYY-MM-DD. For a named month, the last day of that month, "
                       "e.g. 2026-03-31.",
    },
    "last_n_days": {
        "type": "integer",
        "description": "Use for 'past/last N days/weeks': number of days, "
                       "e.g. past 2 weeks = 14, past 10 days = 10, today = 1.",
    },
    "weekday": {
        "type": "string",
        "enum": WEEKDAYS,
        "description": "Use for a single day named by weekday, e.g. 'this Monday', 'last Wednesday'.",
    },
    "week": {
        "type": "string",
        "enum": WEEKS,
        "description": "Only together with weekday: 'this' = this week, 'last' = last week. Default: this.",
    },
}

LIMIT_PARAM = {
    "limit": {
        "type": "integer",
        "description": "How many rows to return, 1-20. Default: 10.",
    },
}

#the same parameters with suffix 1 and 2
COMPARE_PARAMS = {}
for name, spec in TIME_PARAMS.items():
    COMPARE_PARAMS[name + "1"] = spec
    COMPARE_PARAMS[name + "2"] = spec

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_usage_summary",
            "description": "Overall i2b2 usage in a time range: number of queries, average query complexity, "
                           "number of distinct concepts used, queries with temporal constraints, "
                           "average queries per active user, total registered users.",
            "parameters": {"type": "object", "properties": TIME_PARAMS},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_most_active_users",
            "description": "Most active users in a time range, ranked by activity score = queries x 3 + valid sessions "
                           "(sessions with at least 1 query). Returns per user: user_id, query_count, valid_sessions.",
            "parameters": {"type": "object", "properties": {**TIME_PARAMS, **LIMIT_PARAM}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_failed_queries",
            "description": "Number of failed queries in a time range. A query counts as failed if its status is "
                           "INCOMPLETE, ERROR or TIMEDOUT. Returns failed_queries, total_queries and failed_percentage.",
            "parameters": {"type": "object", "properties": TIME_PARAMS},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_slowest_queries",
            "description": "Slowest query runs in a time range, slowest first. Use for questions about slow queries "
                           "or performance. Returns per query: name, user_id, duration_seconds, status.",
            "parameters": {"type": "object", "properties": {**TIME_PARAMS, **LIMIT_PARAM}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_most_searched_concepts",
            "description": "Concepts (diagnoses, lab values, medications, procedures, demographics) used most often "
                           "in queries in a time range. Returns per concept: concept name and number of queries using it.",
            "parameters": {"type": "object", "properties": {**TIME_PARAMS, **LIMIT_PARAM}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_new_users",
            "description": "Number of new user accounts registered in a time range. Returns new_users.",
            "parameters": {"type": "object", "properties": TIME_PARAMS},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_notactive_users",
            "description": "Registered users who ran no query in a time range. Returns registered_users_total, "
                           "users_without_queries (count) and user_ids (the first few of them).",
            "parameters": {"type": "object", "properties": {**TIME_PARAMS, **LIMIT_PARAM}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_compared_usage",
            "description": "Compares the number of queries in two time ranges, e.g. 'is usage growing compared to "
                           "last month?' or 'compare October with September'. Parameters ending in 1 = the newer "
                           "range the user asks about; ending in 2 = the older range to compare with. If the user "
                           "names only one range, leave all the 2-parameters empty: the previous range of the same "
                           "length is used. For 'this week vs last week' use period1=this_week, period2=last_week. "
                           "Returns queries for both ranges, change, change_percent and trend (up, down, same).",
            "parameters": {"type": "object", "properties": COMPARE_PARAMS},
        },
    },
]


#whitelist: only these functions can be called by the model
AVAILABLE = {
    "get_usage_summary": get_usage_summary,
    "get_most_active_users": get_most_active_users,
    "get_failed_queries": get_failed_queries,
    "get_slowest_queries": get_slowest_queries,
    "get_most_searched_concepts": get_most_searched_concepts,
    "get_new_users": get_new_users,
    "get_notactive_users": get_notactive_users,
    "get_compared_usage": get_compared_usage,
}


#errors go back to the model as text
def run_tool(name, args):
    if name not in AVAILABLE:
        return {"error": f"Unknown tool: {name}. Use one of {list(AVAILABLE)}"}
    try:
        return AVAILABLE[name](**args)
    except (ValueError, TypeError) as error:
        return {"error": str(error)}
