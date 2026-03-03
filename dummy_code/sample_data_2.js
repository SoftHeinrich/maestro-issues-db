// Fisher-Yates Shuffle to randomize the order of issues
function shuffle(array) {
  for (let i = array.length - 1; i > 0; i--) {
    let j = Math.floor(Math.random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
}

// Function to process a single project
function processProject(
  projectKeyPrefix,
  architecturalLimit,
  nonArchitecturalLimit
) {
  // Switch to the 'db1' database
  var db1 = db.getSiblingDB("JiraRepos");

  // Query the 'Apache' collection in 'db1' for the given project key prefix
  var issues = db1.Apache.aggregate([
    { $match: { key: new RegExp("^" + projectKeyPrefix + "-") } },
    { $sample: { size: 2000 } }, // Randomly select 200 documents
  ]).toArray();

  // Get all issue IDs
  var issueIds = issues.map((issue) => "Apache-" + issue.id);

  // Switch to the 'db2' database
  var db2 = db.getSiblingDB("MiningDesignDecisions");

  var model_id = "648ee4526b3fde4b1b33e099-648f1f6f6b3fde4b1b3429cf";

  // Fetch all decision details for the issues in a single query
  var decisionDetailsMap = {};
  db2.IssueLabels.find({ _id: { $in: issueIds } }).forEach(function (
    decision_details
  ) {
    decisionDetailsMap[decision_details._id] = decision_details;
  });

  // Counters for tracking how many decisions have been saved
  var architecturalCount = 0;
  var nonArchitecturalCount = 0;

  issues.forEach(function (issue) {
    var decisionId = "Apache" + "-" + issue.id;
    // console.log(decisionId);
    var decision_details = decisionDetailsMap[decisionId];

    if (
      decision_details &&
      decision_details.predictions &&
      decision_details.predictions[model_id]
    ) {
      var isArchitecturalDecision =
        decision_details.predictions[model_id].existence["prediction"] ||
        decision_details.predictions[model_id].executive["prediction"] ||
        decision_details.predictions[model_id].property["prediction"];

      if (isArchitecturalDecision && architecturalCount < architecturalLimit) {
        // Save to the Architectural collection for the project
        db1.SampleApache.insertOne(issue);
        architecturalCount++;
      } else if (
        !isArchitecturalDecision &&
        nonArchitecturalCount < nonArchitecturalLimit
      ) {
        // Save to the Non_architectural collection for the project
        db1.SampleApache.insertOne(issue);
        nonArchitecturalCount++;
      }
    }

    // Stop processing if we have reached the required number of decisions
    if (
      architecturalCount >= architecturalLimit &&
      nonArchitecturalCount >= nonArchitecturalLimit
    ) {
      return false; // Exit the forEach loop
    }
  });

  console.log(
    "Saved",
    architecturalCount,
    "architectural decisions for",
    projectKeyPrefix
  );
  console.log(
    "Saved",
    nonArchitecturalCount,
    "non-architectural decisions for",
    projectKeyPrefix
  );
}

// List of projects with their respective architectural and non-architectural limits
var projects = [
  { keyPrefix: "CASSANDRA", architecturalLimit: 55, nonArchitecturalLimit: 76 },
  { keyPrefix: "HADOOP", architecturalLimit: 44, nonArchitecturalLimit: 40 },
  { keyPrefix: "HDFS", architecturalLimit: 34, nonArchitecturalLimit: 38 },
  { keyPrefix: "MAPREDUCE", architecturalLimit: 10, nonArchitecturalLimit: 16 },
  { keyPrefix: "TAJO", architecturalLimit: 14, nonArchitecturalLimit: 19 },
  { keyPrefix: "YARN", architecturalLimit: 27, nonArchitecturalLimit: 31 },

  // Add more projects here
];

// Process each project
projects.forEach(function (project) {
  processProject(
    project.keyPrefix,
    project.architecturalLimit,
    project.nonArchitecturalLimit
  );
});
