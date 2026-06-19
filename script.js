/**
 * CycleBubble 可交互 Demo
 * 底部 Tab 切换功能区 + 共鸣页连续翻阅下一条
 */
(function () {
  "use strict";

  // ====== Tab 切换 ======
  function switchTo(name) {
    var screens = document.querySelectorAll(".screen");
    for (var i = 0; i < screens.length; i++) {
      screens[i].classList.remove("active");
    }
    var target = document.querySelector('.screen[data-screen="' + name + '"]');
    if (target) {
      target.classList.add("active");
      var body = target.querySelector(".screen-body");
      if (body) body.scrollTop = 0;
    }

    // 更新 Tab 高亮（只对主 Tab）
    var tabs = document.querySelectorAll(".tab-item");
    for (var j = 0; j < tabs.length; j++) {
      tabs[j].classList.remove("active");
    }
    var activeTab = document.querySelector('.tab-item[data-goto="' + name + '"]');
    if (activeTab) activeTab.classList.add("active");
  }

  // 绑定 Tab 点击
  var tabItems = document.querySelectorAll(".tab-item");
  for (var t = 0; t < tabItems.length; t++) {
    tabItems[t].addEventListener("click", function () {
      switchTo(this.getAttribute("data-goto"));
    });
  }

  // 绑定返回按钮
  var backEls = document.querySelectorAll("[data-back]");
  for (var b = 0; b < backEls.length; b++) {
    backEls[b].addEventListener("click", function () {
      switchTo(this.getAttribute("data-back"));
    });
  }

  // 绑定普通跳转链接
  var gotoEls = document.querySelectorAll("[data-goto]");
  for (var g = 0; g < gotoEls.length; g++) {
    if (!gotoEls[g].classList.contains("tab-item")) {
      gotoEls[g].addEventListener("click", function (e) {
        e.preventDefault();
        switchTo(this.getAttribute("data-goto"));
      });
    }
  }

  // ====== 记录页：标签选择 ======
  var selectedChips = [];
  var chipBtns = document.querySelectorAll("#chips button");
  for (var c = 0; c < chipBtns.length; c++) {
    chipBtns[c].addEventListener("click", function () {
      this.classList.toggle("selected");
      var chip = this.getAttribute("data-chip");
      var idx = selectedChips.indexOf(chip);
      if (idx > -1) selectedChips.splice(idx, 1);
      else selectedChips.push(chip);
    });
  }

  // ====== 记录页：保存 → AI 理解 ======
  var saveBtn = document.getElementById("saveBtn");
  var aiProcessing = document.getElementById("aiProcessing");
  var aiResult = document.getElementById("aiResult");
  var recordInput = document.getElementById("recordInput");

  if (saveBtn) {
    saveBtn.addEventListener("click", function () {
      var text = recordInput ? recordInput.value.trim() : "";

      if (!text && selectedChips.length === 0) {
        if (recordInput) {
          recordInput.value = "今天会议里有一句评价，我一直反复想起。好像不是那句话本身，而是我很在意自己有没有被认可。";
        }
      }

      if (selectedChips.length === 0) {
        var defaultChip = document.querySelector('#chips button[data-chip="被评价"]');
        if (defaultChip) {
          defaultChip.classList.add("selected");
          selectedChips.push("被评价");
        }
      }

      saveBtn.style.display = "none";
      aiProcessing.hidden = false;

      setTimeout(function () {
        aiProcessing.hidden = true;
        aiResult.hidden = false;

        var resultText = aiResult.querySelector("p:not(.label):not(.link-row)");
        if (resultText && selectedChips.length > 0) {
          var chipStr = selectedChips.join("、");
          resultText.innerHTML =
            "你提到的场景，和 <strong>" + chipStr + "</strong> 有关。这类感受在<strong>黄体期</strong>更容易出现。";
        }
      }, 2000);
    });
  }

  // ====== 共鸣页：连续翻阅 ======
  var resonanceCards = document.querySelectorAll(".resonance-card");
  var pageDots = document.querySelectorAll("#pageDots i");
  var pagerHint = document.getElementById("pagerHint");
  var currentIndex = 0;
  var totalCards = resonanceCards.length;

  function updatePager() {
    for (var d = 0; d < pageDots.length; d++) {
      pageDots[d].classList.remove("active");
    }
    if (pageDots[currentIndex]) pageDots[currentIndex].classList.add("active");

    if (currentIndex >= totalCards - 1) {
      if (pagerHint) pagerHint.textContent = "这是最后一条，看看你的规律 →";
    } else {
      if (pagerHint) pagerHint.textContent = "回应后自动看到下一条";
    }
  }

  function nextCard() {
    if (currentIndex >= totalCards - 1) return;

    // 当前卡片滑出
    resonanceCards[currentIndex].classList.remove("active");
    resonanceCards[currentIndex].classList.add("leaving");

    setTimeout(function () {
      resonanceCards[currentIndex].classList.remove("leaving");
      currentIndex++;
      resonanceCards[currentIndex].classList.add("active");
      updatePager();
    }, 450);
  }

  // 绑定共鸣卡片的"我也有过"和"谢谢你"按钮
  var empathyBtns = document.querySelectorAll(".empathy-btn");
  var thankBtns = document.querySelectorAll(".thank-btn");

  for (var e = 0; e < empathyBtns.length; e++) {
    empathyBtns[e].addEventListener("click", function () {
      this.classList.add("responded");
      this.textContent = "已表达";
      this.disabled = true;

      // 1.2 秒后自动滑到下一条
      var self = this;
      setTimeout(function () {
        nextCard();
      }, 1200);
    });
  }

  for (var th = 0; th < thankBtns.length; th++) {
    thankBtns[th].addEventListener("click", function () {
      this.classList.add("responded");
      this.textContent = "已感谢";
      this.disabled = true;

      var self = this;
      setTimeout(function () {
        nextCard();
      }, 1200);
    });
  }

  // 初始化
  updatePager();

})();
