<script setup lang="ts">
defineProps<{ mode: 'poll' | 'epoll' | 'uring' }>()
</script>

<template>
  <div class="io-flow" :data-mode="mode">
    <div class="io-lane-head"><strong>Application</strong><span>{{ mode === 'uring' ? '共有リング' : '依頼 → / 結果 ←' }}</span><strong>Linux Kernel</strong></div>
    <template v-if="mode === 'poll'">
      <div class="io-lane"><div><b class="ref-fd">fd一覧 A・B</b>を毎回渡す</div><span class="io-arrow">→</span><div><b class="ref-operation">poll</b>：Ready状態を確認</div></div>
      <div class="io-lane"><div><b class="ref-result">revents</b>を確認する</div><span class="io-arrow">←</span><div><b class="ref-fd">fd B がReady</b></div></div>
      <div class="io-lane"><div><b class="ref-operation">read(fd B)</b> → <b class="ref-buffer">hello</b></div><span class="io-arrow io-roundtrip">⇄</span><div>データはここで読み取る</div></div>
    </template>
    <template v-else-if="mode === 'epoll'">
      <div class="io-lane io-registration"><div><b class="ref-operation">create1 → ctl ADD</b></div><span class="io-arrow">→</span><div><b class="ref-fd">監視集合 A・B を保持</b></div></div>
      <div class="io-lane"><div><b class="ref-operation">epoll_wait</b>で待つ</div><span class="io-arrow io-roundtrip">⇄</span><div><b class="ref-fd">fd B がReady</b></div></div>
      <div class="io-lane"><div><b class="ref-operation">read(fd B)</b> → <b class="ref-buffer">hello</b></div><span class="io-arrow io-roundtrip">⇄</span><div>データはここで読み取る</div></div>
    </template>
    <template v-else>
      <div v-click="1" class="io-lane"><div><b class="ref-operation">READのSQE</b>を準備</div><span class="io-arrow">→</span><div><b>SQ</b>：<b class="ref-result">user_data=42</b></div></div>
      <div v-click="2" class="io-lane"><div><b class="ref-operation">submit</b> → io_uring_enterで通知</div><span class="io-arrow">→</span><div><b class="ref-fd">pipeのfd</b>から読み取る</div></div>
      <div v-click="3" class="io-lane"><div><b class="ref-operation">CQE取得</b> → <b v-click="4" class="ref-buffer">bufferにhello</b></div><span class="io-arrow">←</span><div><b>CQ</b>：<b class="ref-result">user_data=42 / res=5</b></div></div>
    </template>
  </div>
</template>
