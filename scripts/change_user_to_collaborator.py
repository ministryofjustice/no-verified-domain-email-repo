import sys
import time
import traceback
from datetime import datetime, timedelta
from ghapi.all import GhApi
from gql import gql, Client
from gql.transport.aiohttp import AIOHTTPTransport

# Get the GH Action token
oauth_token = sys.argv[1]

# Calculate the dates for API queries
today_date = datetime.now().isoformat()
two_weeks_ago = (datetime.now() - timedelta(weeks=(2))).isoformat()

# The GH REST API interface
api = GhApi(
    owner="ministryofjustice",
    repo="no-verified-domain-email-repo",
    token=oauth_token,
)


def print_stack_trace(message):
    """This will attempt to print a stack trace when an exception occurs
    Args:
        message ([type]): A message to print when exception occurs
    """
    print(message)
    try:
        exc_info = sys.exc_info()
    finally:
        traceback.print_exception(*exc_info)
        del exc_info


# Setup a transport and client to interact with the GH GraphQL API
try:
    transport = AIOHTTPTransport(
        url="https://api.github.com/graphql",
        headers={"Authorization": "Bearer {}".format(oauth_token)},
    )
except Exception:
    print_stack_trace("Exception: Problem with the API URL or GH Token")

try:
    client = Client(transport=transport, fetch_schema_from_transport=False)
except Exception:
    print_stack_trace("Exception: Problem with the Client.")


def repo_issues_query(after_cursor=None) -> gql:
    """A GraphQL query to get the repo list of issues for no-verified-domain-email-repo
    Args:
        after_cursor ([type], optional): Is the pagination offset value gathered from the previous API request. Defaults to None.
    Returns:
        gql: The GraphQL query result
    """
    query = """
    {
        repository(name: "no-verified-domain-email-repo", owner: "ministryofjustice") {
            issues(first: 100, after:AFTER) {
                pageInfo {
                    endCursor
                    hasNextPage
                }
                edges {
                    node {
                        number
                        state
                        createdAt
                        assignees(first: 10) {
                            edges {
                                node {
                                    login
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    """.replace(
        # This is the next page ID to start the fetch from
        "AFTER",
        '"{}"'.format(after_cursor) if after_cursor else "null",
    )

    return gql(query)


def fetch_repo_issues() -> list:
    """A wrapper function to run a GraphQL query to get the list of issues in a repo
    Returns:
        list: A list of issues for a repo
    """
    issue_list = []
    has_next_page = True
    after_cursor = None

    while has_next_page:
        query = repo_issues_query(after_cursor)
        data = client.execute(query)

        # Loop through the issues
        for issue in data["repository"]["issues"]["edges"]:
            issue_list.append(issue["node"])

        # Read the GH API page info section to see if there is more data to read
        has_next_page = data["repository"]["issues"]["pageInfo"]["hasNextPage"]
        after_cursor = data["repository"]["issues"]["pageInfo"]["endCursor"]

    return issue_list


def close_issue(issue_number):
    """Close an issue within the no-verified-domain-email-repo
    Args:
        issue_number (bool): The issue to close
    """
    #
    api.issues.update(
        owner="ministryofjustice",
        repo="no-verified-domain-email-repo",
        issue_number=issue_number,
        state="closed",
    )

    print("Closed isssue number {0}".format(issue_number))

    # Delay for GH API
    time.sleep(5)


def run():
    """A function for the main functionality of the script"""

    # Get the no-verified-domain-email-repo issues list
    repo_issues = fetch_repo_issues()

    for repo_issue in repo_issues:
        if repo_issue["state"] == "OPEN":
            if repo_issue["createdAt"] > two_weeks_ago:
                # It has been less than two weeks
                pass
            else:
                # Check a user hasn't un-assigned themselves from the issue
                if repo_issue["assignees"]["edges"]:
                    user_name = repo_issue["assignees"]["edges"][0]["node"]["login"]
                    try:
                        # Change user to outside collaborator
                        api.orgs.convert_member_to_outside_collaborator(
                            "ministryofjustice", user_name
                        )

                        print("Changed user to an outside collaborator: " + user_name)

                        # Delay for GH API
                        time.sleep(5)

                        # Close the issue in the repo as it will remain open
                        close_issue(repo_issue["number"])

                    except Exception:
                        message = (
                            "Warning: Exception in changing the user to outside collaborator for "
                            + user_name
                        )
                        print_stack_trace(message)
                        # Back off from GH API
                        time.sleep(30)


print("Start")
run()
print("Finished")
sys.exit(0)
