Feature: Daily model visualization acceptance

  Scenario: Browse the generated catalog
    Given the built Model Vis site is running
    When I open the model catalog
    Then 51 generated models are listed

  Scenario: Inspect semantic stages
    Given the built Model Vis site is running
    When I inspect DINOv3 semantic architecture
    Then semantic stages and exact tags are shown

  Scenario: Run Tensor Journey
    Given the built Model Vis site is running
    When I run the DINOv3 Tensor Journey
    Then journey steps use generated tensors

  Scenario: Compare models
    Given the built Model Vis site is running
    When I compare Moshi with DINOv3
    Then normalized stages and config results are shown

  Scenario: Inspect distributions
    Given the built Model Vis site is running
    When I inspect DINOv3 parameter and operation distributions
    Then both mapped distributions are visible
