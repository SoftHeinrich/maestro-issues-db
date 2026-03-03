from time import sleep
from time import time  # To time the duration of the requests

import requests  # To get the data
import urllib3
from app.dependencies import jira_repos_db, issue_labels_collection
from app.exceptions import url_not_working_exception
from jira import JIRA

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Apache projects requiring authentication
APACHE_AUTH_PROJECTS = [
    "DATALAB",
    "CLOUDSTACK",
    "COUCHDB",
    "DAYTRADER",
    "DELTASPIKE",
    "GERONIMO",
    "GSHELL",
    "INFRA",
    "MYNEWT",
    "RIVER",
    "SANTUARIO",
    "SOLR",
    "XALANJ",
    "YOKO",
]


def check_jira_url(jira_url):
    try:
        requests.head(jira_url)
    except ConnectionError:
        raise url_not_working_exception(jira_url)

    # CHECK PROVIDED JIRA URL API AVAILABILITY
    response = requests.get(jira_url + "/rest/api/2/issuetype")
    if response.status_code >= 300:
        return url_not_working_exception(jira_url)

    # CHECK NUMBER OF ISSUES
    response = requests.get(jira_url + "/rest/api/2/search?jql=&maxResults=0")
    if response.status_code >= 300:
        return url_not_working_exception(jira_url)


def format_duration(start_time, end_time):
    # Get the total seconds of the duration
    seconds = end_time - start_time
    # Calculate the other time
    milliseconds = int((seconds % 1) * 10000)
    minutes = int(seconds / 60)
    hours = int(minutes / 60)
    # Trim the values to fit in their appopriate slots
    display_minutes = int(minutes % 60)
    display_seconds = int(seconds % 60)

    return f"{hours:02}:{display_minutes:02}:{display_seconds:02}.{milliseconds:04}"


def get_jira_server(jira_name, url, enable_auth=False, username=None, password=None):
    check_jira_url(url)
    if enable_auth and jira_name == "Apache":
        return JIRA(url, basic_auth=(username, password))
    return JIRA(url)


def get_response(jira, download_date, start_index, iteration_max=100):
    if download_date is None:
        query = f"order by created asc"
    else:
        query = f'updated>="{download_date}" order by created asc'
    return jira.search_issues(
        query,
        startAt={start_index},
        maxResults={iteration_max},
        expand="changelog",
        json_result=True,
    )


def download_and_write_data_mongo(
    jira_name,
    jira_server,
    download_date,
    num_desired_results=None,  # Leave as "None" to download all, otherwise specify a number
    iteration_max=250,  # Recommended to keep at or below 500
    start_index=0,  # This allows you to start back up from a different place
    num_available_results=None,
    enable_auth=False,
):
    collection = jira_repos_db[jira_name]

    # iteration_max is the number of issues the script will attempt to get at one time.
    # The Jira default max is 1000. Trying with 1000 consistently returned errors after a short while
    # as the object being returned was likely too large. Values of 500 or less serve no particular issue
    # to the script except that more calls (of smaller size) have to be made.

    # How many issues to collect before writing to MongoDB
    num_issues_per_write = 10000

    last_write_start_index = start_index
    issues = []

    if num_available_results is None:
        # Available and requested number of results
        num_available_results = get_response(jira_server, download_date, 0, 0)["total"]
        print(
            f'Number of Desired Results   : {num_desired_results if num_desired_results else "All"}'
        )
        print(f"Number of Available Results : {num_available_results}")
        print("")

    # Set the number of results to retrieve based on information from Jira server
    if not num_desired_results:
        num_remaining_results = num_available_results
    else:
        num_remaining_results = min(int(num_desired_results), num_available_results)
    # Adjust remaining results based on their start index
    num_remaining_results -= start_index

    # Collect results while there are more results to gather
    issues_downloaded = 0
    max_count_width = len(str(num_remaining_results)) + 1
    print(f"Total Remaining:{num_remaining_results:< {max_count_width}}")
    while num_remaining_results > 0:
        # Start a timer for this particular chunk
        start_time = time()

        # Number of items to retrieve
        num_items_to_retrieve = min(iteration_max, num_remaining_results)

        # Get issues from Jira
        response_json = get_response(
            jira_server, download_date, start_index, num_items_to_retrieve
        )
        if "issues" in response_json:
            # Add issues to program list
            issues.extend(response_json["issues"])
            num_returned_issues = len(response_json["issues"])

        # Adjust the remaining results to get
        num_remaining_results -= num_returned_issues

        # Print progress for user
        end_index = start_index + num_returned_issues - 1
        print(
            f"Total Remaining:{num_remaining_results:< {max_count_width}}  "
            f"Retrieved Items: {start_index:< {max_count_width}} - {end_index:< {max_count_width}}  "
            f"Duration: {format_duration(start_time, time())}"
        )

        # Move the start index
        start_index += num_returned_issues

        # Write the issues to file IF there are enough of them. This is a nice way to save state and start over at a
        # certain place if there are too many to download in one go.
        if (
            len(issues) >= num_issues_per_write
            or num_remaining_results == 0
            or num_returned_issues == 0
        ):
            # Delete existing issues before updating
            for issue in issues:
                # Remove old tag
                old_issue = collection.find_one({"id": issue["id"]})
                if not old_issue:
                    continue
                old_tag = old_issue["key"].split("-")[0]
                issue_labels_collection.update_one(
                    {"_id": f"{jira_name}-{issue['id']}"},
                    {"$pull": {"tags": f"{jira_name}-{old_tag}"}},
                )
            ids = [issue["id"] for issue in issues]
            collection.delete_many({"id": {"$in": ids}})

            # Write the data to mongodb
            collection.insert_many(issues)
            for issue in issues:
                issue_label = issue_labels_collection.find_one(
                    {"_id": f"{jira_name}-{issue['id']}"}
                )
                if issue_label is None:
                    issue_labels_collection.insert_one(
                        {
                            "_id": f"{jira_name}-{issue['id']}",
                            "existence": None,
                            "property": None,
                            "executive": None,
                            "tags": [],
                            "comments": {},
                            "predictions": {},
                        }
                    )
                new_tag = issue["key"].split("-")[0]
                issue_labels_collection.update_one(
                    {"_id": f"{jira_name}-{issue['id']}"},
                    {"$addToSet": {"tags": f"{jira_name}-{new_tag}"}},
                )

            print("... Issues written to database ...")
            last_write_start_index = start_index

            issues_downloaded += len(issues)
            issues = []  # Clear the issues so that our memory doesn't get too full

        # If we have for some reason run out of results, we may want to react to this in some way
        if num_returned_issues == 0:
            print(
                "Number of Returned Issues is 0. This is strange and should not happen. Investigate."
            )
            return

    print("")
    print(f"Number of Downloaded Issues: {issues_downloaded}")


def download_multiprocessed(
    jira_name,
    url,
    download_date,
    batch_size,
    query_wait_time_minutes,
    enable_auth,
    username=None,
    password=None,
    start_index=0,
):
    # Available and requested number of results
    jira_server = get_jira_server(
        jira_name, url, enable_auth=enable_auth, username=username, password=password
    )
    num_available_results = get_response(jira_server, download_date, 0, 0)["total"]
    print(f"Total issues to download from {jira_name}: {num_available_results}")
    while start_index + batch_size <= num_available_results:
        download_and_write_data_mongo(
            jira_name,
            jira_server,
            download_date,
            start_index + batch_size,
            batch_size,
            start_index,
            num_available_results,
            enable_auth,
        )
        start_index += batch_size
        sleep(query_wait_time_minutes)
    download_and_write_data_mongo(
        jira_name,
        jira_server,
        download_date,
        num_available_results,
        batch_size,
        start_index,
        num_available_results,
        enable_auth,
    )
