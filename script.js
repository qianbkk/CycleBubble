/**
 * CycleBubble 可交互 Demo
 * 核心路径：今日 → 记录 → 共鸣 → 规律 → 理解自己
 */
(function () {
  "use strict";

  var screenLabels = {
    home: "今日",
    cycle: "周期",
    record: "记录",
    resonance: "共鸣",
    pattern: "规律"
  };

  // ====== 屏幕切换 ======
  function switchTo(name) {
    var screens = document.querySelectorAll(".screen");
    for (var i = 0; i < screens.length; i++) {
      screens[i].classList.remove("active");
    }
    var target = document.querySelector('.screen[data-screen="' + name + '"]');
    if (target) {
      target.classList.add("active");
      target.scrollTop = 0;
    }

    var tabs = document.querySelectorAll(".tabbar span");
    for (var j = 0; j < tabs.length; j++) {
      tabs[j].classList.remove("active");
    }
    var activeTab = document.querySelector('.tabbar span[data-goto="' + name + '"]');
    if (activeTab) activeTab.classList.add("active");

    var label = document.getElementById("statusLabel");
    if (label) label.textContent = screenLabels[name] || "";
  }

  // 绑定所有 data-goto 元素（Tab、按钮、链接）
  var gotoEls = document.querySelectorAll("[data-goto]");
  for (var i = 0; i < gotoEls.length; i++) {
    gotoEls[i].addEventListener("click", function (e) {
      e.preventDefault();
      switchTo(this.getAttribute("data-goto"));
    });
  }

  // ====== 记录页：标签选择 ======
  var selectedChips = [];
  var chipBtns = document.querySelectorAll("#chips button");
  for (var c = 0; c < chipBtns.length; c++) {
    chipBtns[c].addEventListener("click", function () {
      this.classList.toggle("selected");
      var chip = this.getAttribute("data-chip");
      var idx = selectedChips.indexOf(chip);
      if (idx > -1) {
        selectedChips.splice(idx, 1);
      } else {
        selectedChips.push(chip);
      }
    });
  }

  // ====== 记录页：保存 → AI 理解过程 ======
  var saveBtn = document.getElementById("saveBtn");
  var aiProcessing = document.getElementById("aiProcessing");
  var aiResult = document.getElementById("aiResult");
  var recordInput = document.getElementById("recordInput");

  if (saveBtn) {
    saveBtn.addEventListener("click", function () {
      var text = recordInput ? recordInput.value.trim() : "";

      // 如果用户没写内容也没选标签，用默认内容
      if (!text && selectedChips.length === 0) {
        if (recordInput) {
          recordInput.value = "今天会议里有一句评价，我一直反复想起。好像不是那句话本身，而是我很在意自己有没有被认可。";
        }
        text = recordInput.value.trim();
      }

      // 如果没选标签，自动选"被评价"
      if (selectedChips.length === 0) {
        var defaultChip = document.querySelector('#chips button[data-chip="被评价"]');
        if (defaultChip) {
          defaultChip.classList.add("selected");
          selectedChips.push("被评价");
        }
      }

      // 隐藏保存按钮，显示 AI 过程态
      saveBtn.style.display = "none";
      aiProcessing.hidden = false;

      // 模拟 AI 理解过程（2 秒）
      setTimeout(function () {
        aiProcessing.hidden = true;
        aiResult.hidden = false;

        // 根据用户选的标签更新结果文案
        var resultText = aiResult.querySelector("p:not(.label)");
        if (resultText && selectedChips.length > 0) {
          var chipStr = selectedChips.join("、");
          resultText.innerHTML =
            "你提到的场景，和 <strong>" + chipStr + "</strong> 有关。这类感受在<strong>黄体期</strong>更容易出现。";
        }

        // 3 秒后自动跳转到共鸣页
        setTimeout(function () {
          switchTo("resonance");
          // 重置记录页状态，方便再次体验
          setTimeout(function () {
            saveBtn.style.display = "";
            aiResult.hidden = true;
            aiProcessing.hidden = true;
          }, 500);
        }, 2800);
      }, 2000);
    });
  }

  // ====== 共鸣页：我也有过 ======
  var empathyBtn = document.getElementById("empathyBtn");
  var empathyFeedback = document.getElementById("empathyFeedback");

  if (empathyBtn) {
    empathyBtn.addEventListener("click", function () {
      this.style.background = "var(--coral)";
      this.style.color = "#fffdfb";
      this.textContent = "已表达";
      this.disabled = true;
      if (empathyFeedback) empathyFeedback.hidden = false;
    });
  }

  // ====== 泡泡液面随周期天数变化 ======
  // 周期第 21 天（黄体期），液面较高
  var bubbleLiquid = document.getElementById("bubbleLiquid");
  if (bubbleLiquid) {
    // 62% 是默认高度，黄体期接近满
    bubbleLiquid.style.height = "68%";
  }

})();
