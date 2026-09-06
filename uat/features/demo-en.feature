Feature: English product introduction recording for Model Structure Viewer

  Scenario: Introduce semantic architecture, trace evidence, and comparison
    Given the built Model Vis site is running
    And I begin a recorded demo
    When I open the model catalog
    And I narrate in English for at least 9 seconds: Model Structure Viewer turns generated PyTorch architecture metadata into an offline interactive catalog of one hundred and one models, without downloading weights or running remote model code.
    And I inspect DINOv3 semantic architecture
    Then semantic stages and exact tags are shown
    When I open a semantic stage explanation
    Then the explanation, Tensor Journey, and mapped distributions are visible
    And I narrate in English for at least 11 seconds: Beginner view groups technical modules into meaningful stages. Select a stage to read its purpose, follow the generated tensor journey, and compare how parameters and operations are distributed.
    When I switch the demonstration to Trace source evidence
    Then source lines, runtime facts, and configuration choices are available
    And I narrate in English for at least 11 seconds: Trace view exposes modules, operations, runtime facts, redistributed source lines, and the difference between pinned official configuration and the compact trace configuration.
    When I compare Moshi with DINOv3
    Then normalized stages, exact tags, distributions, and config results are shown
    And I narrate in English for at least 10 seconds: Comparison normalizes two different model families by stage, exact interface tags, trace distributions, and configuration differences, while keeping the original evidence available for inspection.
    Then I finish the recorded demo
