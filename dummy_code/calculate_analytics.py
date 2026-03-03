import json
from collections import defaultdict

# Load the JSON data from the file
with open('sample_apache_data.json', 'r') as file:
    data = json.load(file)

# Define possible prediction values
prediction_types = ['executive', 'existence', 'property']
prediction_states = ['executive', 'existence', 'property', 'non_executive', 'non_existence', 'non_property']

# Function to get combination key
def get_combination_key(issue_predictions, comment_predictions):
    # print(issue_predictions.get('executive', {}).get('prediction', False),issue_predictions.get('existence', {}).get('prediction', False),issue_predictions.get('property', {}).get('prediction', False))
    issue_key = '-'.join(['executive' if issue_predictions.get('executive', {}).get('prediction', False) else 'non_executive',
                          'existence' if issue_predictions.get('existence', {}).get('prediction', False) else 'non_existence',
                          'property' if issue_predictions.get('property', {}).get('prediction', False) else 'non_property'])
    
    comment_key = '-'.join(['executive' if comment_predictions.get('executive', {}).get('prediction', False) else 'non_executive',
                            'existence' if comment_predictions.get('existence', {}).get('prediction', False) else 'non_existence',
                            'property' if comment_predictions.get('property', {}).get('prediction', False) else 'non_property'])
    
    return f"{issue_key}--{comment_key}"


# Initialize combinations count with all possible combinations
combinations_count = defaultdict(int)

# Process each issue in the data
for issue in data:
    issue_predictions = issue.get('predictions', {})
    issue_predictions = issue_predictions.get("648ee4526b3fde4b1b33e099-648f1f6f6b3fde4b1b3429cf",{})
    comment_predictions = issue.get('comments_predictions', [])
    
    for comment in comment_predictions:
        comment_pred = comment[3]
        combination_key = get_combination_key(issue_predictions, comment_pred)
        combinations_count[combination_key] += 1

# Total number of issue-comment pairs processed
total_pairs = sum(combinations_count.values())

# Calculate percentages for each combination
analytics = []
for combination, count in combinations_count.items():
    analytics.append({
        "combination": combination,
        "count": count,
        "percentage": (count / total_pairs) * 100 if total_pairs > 0 else 0
    })

# Sort analytics by combination for readability
analytics.sort(key=lambda x: x["combination"])

# Save the analytics data to a new JSON file
analytics_json = {
    "total_pairs": total_pairs,
    "analytics": analytics
}

with open('analytics.json', 'w') as file:
    json.dump(analytics_json, file, indent=4)

print("Analytics JSON file created successfully.")