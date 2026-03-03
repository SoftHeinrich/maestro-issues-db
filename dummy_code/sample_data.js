// Switch to the 'db1' database
var db1 = db.getSiblingDB("JiraRepos");

// Query the 'Apache' collection in 'db1'
var issues = db1.Apache.find({ key: /CASSANDRA-/ })
  .limit(200)
  .toArray();

// // Fisher-Yates Shuffle to randomize the order of issues
function shuffle(array) {
  for (let i = array.length - 1; i > 0; i--) {
    let j = Math.floor(Math.random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
}

shuffle(issues); // Randomize the issues array

// Switch to the 'db2' database
var db2 = db.getSiblingDB("MiningDesignDecisions");

var model_id = "648ee4526b3fde4b1b33e099-648f1f6f6b3fde4b1b3429cf";

// Counters for tracking how many decisions have been saved
var architecturalCount = 0;
var nonArchitecturalCount = 0;

issues.forEach(function (issue) {
  var decisionId = "Apache-" + issue.id;
  var decision_details = db2.IssueLabels.findOne({ _id: decisionId });

  if (
    decision_details &&
    decision_details.predictions &&
    decision_details.predictions[model_id]
  ) {
    console.log(decision_details);
    var isArchitecturalDecision =
      decision_details.predictions[model_id].existence["prediction"] ||
      decision_details.predictions[model_id].executive["prediction"] ||
      decision_details.predictions[model_id].property["prediction"];

    if (isArchitecturalDecision && architecturalCount < 55) {
      // Save to the Architectural_cassandra collection
      db2.Architectural_cassandra.insertOne(issue);
      architecturalCount++;
    } else if (!isArchitecturalDecision && nonArchitecturalCount < 76) {
      // Save to the Non_architectural_cassandra collection
      db2.Non_architectural_cassandra.insertOne(issue);
      nonArchitecturalCount++;
    }
  }

  // Stop processing if we have reached the required number of decisions
  if (architecturalCount >= 55 && nonArchitecturalCount >= 76) {
    return false; // Exit the forEach loop
  }
});

console.log("Saved", architecturalCount, "architectural decisions.");
console.log("Saved", nonArchitecturalCount, "non-architectural decisions.");
