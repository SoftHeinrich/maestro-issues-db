import json
from collections import defaultdict

# Load the JSON data from the file
with open('sample_apache_data.json', 'r') as file:
    data = json.load(file)

# Define possible prediction values
prediction_types = ['executive', 'existence', 'property']

# Function to get issue key
def get_issue_key(issue_predictions):
    return '-'.join(['executive' if issue_predictions.get('executive', {}).get('prediction', False) else 'non_executive',
                     'existence' if issue_predictions.get('existence', {}).get('prediction', False) else 'non_existence',
                     'property' if issue_predictions.get('property', {}).get('prediction', False) else 'non_property'])

# Initialize combinations count with all possible combinations
combinations_count = defaultdict(lambda: [0, 0, 0, 0, 0, 0]) # [exec_count, exist_count, prop_count, non_arch_count, total_issues, total_comments]

# Process each issue in the data
for issue in data:
    issue_predictions = issue.get('predictions', {})
    issue_predictions = issue_predictions.get("648ee4526b3fde4b1b33e099-648f1f6f6b3fde4b1b3429cf", {})
    comment_predictions = issue.get('comments_predictions', [])
    
    issue_key = get_issue_key(issue_predictions)
    
    combinations_count[issue_key][4] += 1  # Increment total issues count
    
    for comment in comment_predictions:
        comment_pred = comment[3]
        combinations_count[issue_key][5] += 1  # Increment total comments count
        
        # Count the types of predictions in the comment
        if comment_pred.get('executive', {}).get('prediction', False):
            combinations_count[issue_key][0] += 1  # executive
        if comment_pred.get('existence', {}).get('prediction', False):
            combinations_count[issue_key][1] += 1  # existence
        if comment_pred.get('property', {}).get('prediction', False):
            combinations_count[issue_key][2] += 1  # property
        
        if not (comment_pred.get('executive', {}).get('prediction', False) or
                comment_pred.get('existence', {}).get('prediction', False) or
                comment_pred.get('property', {}).get('prediction', False)):
            combinations_count[issue_key][3] += 1  # non_architectural

# Convert combinations_count to a list for sorting and saving
analytics = []
for combination, counts in combinations_count.items():
    analytics.append({
        "combination": combination,
        "executive_count": counts[0],
        "existence_count": counts[1],
        "property_count": counts[2],
        "non_architectural_count": counts[3],
        "total_issues": counts[4],
        "total_comments": counts[5]
    })

# Sort analytics by combination for readability
analytics.sort(key=lambda x: x["combination"])

# Save the analytics data to a new JSON file
analytics_json = {
    "analytics": analytics
}

with open('analytics_2.json', 'w') as file:
    json.dump(analytics_json, file, indent=4)

print("Analytics JSON file created successfully.")
