const bubbleStates = [
  {
    percent: "68%",
    phase: "黄体期倾向",
    title: "今天的泡泡比较满",
    body: "这不是对你的判断。身体节律可能让一些感受更靠近表面，今天适合把安排留得松一点。"
  },
  {
    percent: "54%",
    phase: "卵泡期倾向",
    title: "泡泡正在变轻，适合慢慢恢复",
    body: "如果你感觉精力回来了，可以从一件小事开始。节奏变好不需要立刻把所有事补完。"
  },
  {
    percent: "73%",
    phase: "排卵期后段",
    title: "泡泡流速有一点快",
    body: "如果外界信息太多，可以先减少入口。晚一点回复、少解释一点，也是一种照顾身体的方式。"
  }
];

const percent = document.querySelector(".bubble-content strong");
const phase = document.querySelector(".bubble-content span");
const readingTitle = document.querySelector(".bubble-reading h3");
const readingBody = document.querySelector(".bubble-reading p:last-child");

let stateIndex = 0;

window.setInterval(() => {
  stateIndex = (stateIndex + 1) % bubbleStates.length;
  const next = bubbleStates[stateIndex];
  percent.textContent = next.percent;
  phase.textContent = next.phase;
  readingTitle.textContent = next.title;
  readingBody.textContent = next.body;
}, 5600);
