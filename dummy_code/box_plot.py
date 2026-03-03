import pymongo
import pickle
import matplotlib.pyplot as plt
import os
import numpy as np

def fetch_data_from_mongodb():
    try:
        # MongoDB connection details (match the Docker Compose settings)
        mongo_client = pymongo.MongoClient("mongodb://localhost:27017/")
        mongo_db = mongo_client["JiraRepos"]
        mongo_collection = mongo_db["Apache"]
        # Query documents where fields.description or fields.summary exist
        documents = mongo_collection.find(
            {"$or": [{"fields.description": {"$exists": True}}, {"fields.summary": {"$exists": True}}]},
            {"fields.description": 1, "fields.summary": 1, "_id": 0}
        )
        
        # Extract descriptions and summaries, ensuring both are strings
        descriptions_summaries = [
            (str(doc.get("fields", {}).get("description", "")) + " " + str(doc.get("fields", {}).get("summary", ""))).strip()
            for doc in documents
        ]
        return descriptions_summaries
        # Query documents where fields.description exists
        # documents = mongo_collection.find({"fields.description": {"$exists": True}}, {"fields.description": 1, "_id": 0, "fields.summary": 1,})
        
        
        # # Extract descriptions
        # # descriptions = [doc["fields"]["description"] for doc in documents if "fields" in doc and "description" in doc["fields"]]
        # descriptions = [
        #     (doc.get("fields", {}).get("description", " ") + " " + doc.get("fields", {}).get("summary", " ")).strip()
        #     for doc in documents
        # ]
        # return descriptions

    except Exception as error:
        print(f"Error fetching data from MongoDB: {error}")

def calculate_description_sizes(descriptions):
    # Calculate the size of each description
    description_sizes = [len(desc) for desc in descriptions if isinstance(desc, str) and desc.strip()]
    return description_sizes


def save_array_to_file(array, file_path):
    # Save the array to a file using pickle
    with open(file_path, 'wb') as file:
        pickle.dump(array, file)

def load_array_from_file(file_path):
    # Load the array from a file using pickle
    with open(file_path, 'rb') as file:
        array = pickle.load(file)
    return array

def draw_box_plot(data, title="Box Plot of Description Sizes"):
    # Calculate quartiles and IQR
    q1 = np.percentile(data, 25)
    q2 = np.percentile(data, 50)
    q3 = np.percentile(data, 75)
    iqr = q3 - q1
    
    # Calculate upper and lower bounds for outliers
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    
    # Filter out outliers
    filtered_data = [val for val in data if lower_bound <= val <= upper_bound]
    
    # Print statistical information
    print(f"Q1 (25th percentile): {q1}")
    print(f"Q2 (50th percentile, median): {q2}")
    print(f"Q3 (75th percentile): {q3}")
    print(f"Interquartile Range (IQR): {iqr}")
    # print(f"Lower Bound for Outliers: {lower_bound}")
    # print(f"Upper Bound for Outliers: {upper_bound}")
    print(f"Number of Outliers: {len(data) - len(filtered_data)}")
    # print(f"Outliers: {[val for val in data if val < lower_bound or val > upper_bound]}")
    
    # Draw a box plot using matplotlib without outliers
    plt.figure(figsize=(10, 6))
    plt.boxplot(filtered_data, showfliers=False)  # exclude outliers
    plt.title(title)
    plt.ylabel('Size of Description')
    plt.grid(True)
    plt.show()
    
def main():
    file_path = 'description_sizes_with_summary.pkl'
    
    if os.path.exists(file_path):
        # Load the array from the file if it exists
        print(f"Loading data from {file_path}...")
        description_sizes = load_array_from_file(file_path)
    else:
        # Fetch data from MongoDB if the file does not exist
        print(f"Fetching data from MongoDB...")
        descriptions = fetch_data_from_mongodb()
        if descriptions:
            description_sizes = calculate_description_sizes(descriptions)
            # Save the array of sizes to a file
            save_array_to_file(description_sizes, file_path)
            print(f"Array of description sizes saved to '{file_path}'.")

    # Debugging: print min, max, and sample of description sizes
    print(f"Data range: {min(description_sizes)} to {max(description_sizes)}")
    print(f"Sample data: {description_sizes[:10]}")

    # Draw the box plot
    draw_box_plot(description_sizes, title="Box Plot of Description Sizes")

if __name__ == "__main__":
    main()
