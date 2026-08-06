Feature: Easy-cheese installation
  Scenario: A cloud host does not need GitHub CLI
    Given a cloud host without the GitHub CLI
    When I install easy-cheese for every supported harness
    Then easy-cheese is installed for every supported harness
    And no command uses the GitHub CLI
