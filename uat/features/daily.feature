Feature: Daily Model Structure Viewer acceptance

  Scenario: Start in the documented professional workspace
    Given the built Model Vis site is running
    When I open the model catalog
    Then 101 generated models are listed
    And Standard detail, Both labels, and Architecture are selected
    And a semantic graph, legend, minimap, and inspector are visible

  Scenario: Search, filter, sort, and recover from no catalog results
    Given the built Model Vis site is running
    When I open the model catalog
    And I search the catalog for Falcon
    Then all generated Falcon models matching the search are listed
    When I search the catalog for a model that does not exist
    Then the catalog reports zero models without changing the open graph
    When I clear the catalog search
    And I choose the first model category
    Then the category filter leaves a nonempty catalog subset
    When I sort the catalog by source count
    Then the source-count sort remains selected and models remain available

  Scenario: Reject an unknown URI and recover with a valid shareable URI
    Given the built Model Vis site is running
    When I open the model catalog
    And I submit an unknown model URI
    Then the unknown-model diagnostic remains visible long enough to read
    When I submit the DINOv3 beginner architecture URI
    Then the DINOv3 URI and semantic graph are restored

  Scenario: Move through every graph mode and detail level
    Given the built Model Vis site is running
    When I inspect DINOv3 semantic architecture
    Then semantic stages and exact tags are shown
    When I select Standard detail
    Then Both labels remain selected on the current semantic stage
    When I select Trace detail
    Then Operations and Source labels are selected with runtime nodes
    When I visit Family, Modules, Blocks, and Operations graph modes
    Then every graph mode renders connected model content
    When I return to Beginner detail
    Then Architecture and Semantic labels return with the same stage selected

  Scenario: Inspect explanations, tensors, source, runtime, and configurations
    Given the built Model Vis site is running
    When I open an Apertus module in Trace detail and select a node
    Then Details shows structural metadata
    When I open the I/O inspector
    Then tensor shape records are visible
    When I open the Source inspector
    Then a source reference, source lines, and official repository link are visible
    When I open the Runtime inspector
    Then runtime rows are visible
    When I open Official, Trace, and Differences configuration views
    Then configuration provenance and changed fields are visible

  Scenario: Follow graph search, tensor routes, zoom, focus, and overlays
    Given the built Model Vis site is running
    When I open an Apertus module in Trace detail and select a node
    And I search the graph for rmsnorm
    Then matching graph nodes are highlighted
    When I follow the selected node outputs
    Then the downstream tensor route is highlighted
    When I zoom out and fit the graph
    Then the zoom indicator changes and the graph remains visible
    When I toggle full canvas, legend, and minimap
    Then the canvas and both overlay states change
    When I reload the viewer
    Then the legend and minimap preferences persist

  Scenario: Persist a dragged and resized layout and reset it
    Given the built Model Vis site is running
    When I open the BERT module workspace
    And I drag and resize a graph node
    Then the custom node layout is stored locally
    When I reload the viewer
    Then the custom node position and size are restored
    When I reset the graph layout
    Then the node returns to its generated position and default size

  Scenario: Persist theme, view preferences, selection, and deep route
    Given the built Model Vis site is running
    When I inspect DINOv3 semantic architecture
    And I select a semantic stage and change theme and labels
    Then the selected stage and explicit choices appear in the URI
    When I reload the viewer
    Then theme, labels, and semantic stage selection persist

  Scenario: Explain comparison selection and compare two model families
    Given the built Model Vis site is running
    When I open the model catalog
    And I open comparison without selecting two models
    Then comparison explains that two models are required
    When I close comparison and select DINOv3 and Moshi
    And I open comparison
    Then normalized stages, exact tags, distributions, and config results are shown
    When I close comparison
    Then the graph workspace is available again

  Scenario: Surface partial model provenance instead of hiding it
    Given the built Model Vis site is running
    When I search for and open the partial DINOv3 record
    Then the catalog badge and inspector warning explain partial official configuration coverage

  Scenario: Navigate modules and source files with search and keyboard
    Given the built Model Vis site is running
    When I open the Data2Vec module workspace
    And I search the module tree for attention
    Then matching hierarchy rows remain visible
    When I use Home, End, Left, and Right in the module tree
    Then keyboard focus and expansion follow tree navigation rules
    When I open the source-file navigator
    Then the source file hierarchy and selected source panel are available

  Scenario: Use catalog and inspector drawers on a mobile viewport
    Given the built Model Vis site is running
    When I open DINOv3 on a mobile viewport
    And I open the catalog drawer
    Then the catalog drawer and scrim are visible
    When I dismiss the drawer and select a graph stage
    Then the mobile inspector drawer opens and can be dismissed

  Scenario: Run Tensor Journey and inspect generated distributions
    Given the built Model Vis site is running
    When I run the DINOv3 Tensor Journey
    Then journey steps use generated tensors
    When I inspect DINOv3 parameter and operation distributions
    Then both mapped distributions are visible

  Scenario: Save and export an annotated investigation
    Given the built Model Vis site is running
    When I save an annotated GELU review and export its facts
    Then the downloaded files preserve GELU and its provenance
    When I restore the saved review from another model
    Then BERT GELU and the saved annotation are restored

  Scenario: Find an exact operation and persist panel sizing
    Given the built Model Vis site is running
    When I filter GELU by module, dtype and shape
    Then the finder identifies the exact GELU interface and opens it
    And my resized catalog panel survives a reload

  Scenario: Compare compatible facts with configuration drilldown
    Given the built Model Vis site is running
    When I compare BERT and Arcee using differences and pinned configs
    Then scope differences and actual configuration values remain visible
