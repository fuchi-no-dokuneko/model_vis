Feature: Model Structure Viewer 粵語產品介紹錄影

  Scenario: 介紹語意架構、追蹤證據同模型比較
    Given the built Model Vis site is running
    And I begin a recorded demo
    When I open the model catalog
    And I narrate in Cantonese for at least 9 seconds: Model Structure Viewer 將產生好嘅 PyTorch 架構資料整理成離線互動目錄，入面有五十一個模型，唔需要下載權重，亦唔會執行遠端模型程式碼。
    And I inspect DINOv3 semantic architecture
    Then semantic stages and exact tags are shown
    When I open a semantic stage explanation
    Then the explanation, Tensor Journey, and mapped distributions are visible
    And I narrate in Cantonese for at least 11 seconds: 初學者模式會將技術模組整理成有意思嘅階段。揀一個階段，就可以睇用途、跟住產生好嘅張量流程，再比較參數同運算分佈。
    When I switch the demonstration to Trace source evidence
    Then source lines, runtime facts, and configuration choices are available
    And I narrate in Cantonese for at least 11 seconds: 追蹤模式會顯示模組、運算、執行資料、可重新發布嘅源碼行，仲可以比較固定官方設定同精簡追蹤設定有咩分別。
    When I compare Moshi with DINOv3
    Then normalized stages, exact tags, distributions, and config results are shown
    And I narrate in Cantonese for at least 10 seconds: 比較功能會按語意階段、精確介面標籤、追蹤分佈同設定差異整理兩個模型，同時保留原始證據畀你逐項檢查。
    Then I finish the recorded demo
