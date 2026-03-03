import json
import matplotlib.pyplot as plt
import numpy as np

# Load the data from the JSON file
with open('analytics_2.json', 'r') as file:
    data = json.load(file)["analytics"]

# Extract the combinations and the corresponding counts
combinations = [item['combination'] for item in data]
total_issues = [item['total_issues'] for item in data]
total_comments = [item['total_comments'] for item in data]
executive_count = [item['executive_count'] for item in data]
existence_count = [item['existence_count'] for item in data]
property_count = [item['property_count'] for item in data]

# Calculate the sum of executive, existence, and property counts for each combination
total_exec_ext_prop = [exec + ext + prop for exec, ext, prop in zip(executive_count, existence_count, property_count)]

# Convert the values to percentages relative to the sum of exec, ext, prop per combination
executive_count_pct = [(exec / total) * 100 if total > 0 else 0 for exec, total in zip(executive_count, total_exec_ext_prop)]
existence_count_pct = [(ext / total) * 100 if total > 0 else 0 for ext, total in zip(existence_count, total_exec_ext_prop)]
property_count_pct = [(prop / total) * 100 if total > 0 else 0 for prop, total in zip(property_count, total_exec_ext_prop)]

# Set the position of the bars on the X axis
x = np.arange(len(combinations))

# Set the width of the bars
bar_width = 0.25

# Create the bar charts
fig, ax = plt.subplots(figsize=(12, 8))
bar1 = ax.bar(x - bar_width, executive_count_pct, bar_width, label='Executive Count %', color='green')
bar2 = ax.bar(x, existence_count_pct, bar_width, label='Existence Count %', color='red')
bar3 = ax.bar(x + bar_width, property_count_pct, bar_width, label='Property Count %', color='purple')

# Add labels, title, and custom x-axis tick labels
ax.set_xlabel('Combination')
ax.set_ylabel('Percentage')
ax.set_title('Percentage of Exec, Ext, Prop Counts per Combination')
ax.set_xticks(x)
ax.set_xticklabels(combinations, rotation=45, ha="right")
ax.legend()

# Add a grid for better readability
ax.grid(True, axis='y', linestyle='--', alpha=0.7)

# Show the plot
plt.tight_layout()
plt.show()
