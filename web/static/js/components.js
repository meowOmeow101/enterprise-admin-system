/* ==========================================================================
   通用 Vue 组件：表格、分页、弹窗、徽标、空状态、卡片等
   全部注册在 window.Components，由 app.js 统一挂到全局
   ========================================================================== */
(function () {
  'use strict';

  const Components = {};

  /* ------------------------------------------------------------ 状态徽标 */
  Components.StatusTag = {
    props: { status: { type: [String, Number], default: '' }, text: { type: String, default: '' } },
    computed: {
      cls: function () { return 'tag ' + App.statusClass(this.status); },
      label: function () { return this.text || this.status || '—'; },
    },
    template: '<span :class="cls">{{ label }}</span>',
  };

  /* ------------------------------------------------------------ KPI 卡片 */
  Components.StatCard = {
    props: {
      label: String,
      value: [String, Number],
      foot: String,
      accent: { type: String, default: '1' },
      icon: { type: String, default: '' },
    },
    template: `
      <div class="card kpi" :class="'accent-' + accent">
        <div class="kpi-label">
          <span v-if="icon" style="margin-right:4px">{{ icon }}</span>{{ label }}
        </div>
        <div class="kpi-value">{{ value }}</div>
        <div class="kpi-foot" v-if="foot">{{ foot }}</div>
      </div>`,
  };

  /* ------------------------------------------------------------ 分页器 */
  Components.Pagination = {
    props: {
      page: { type: Number, default: 1 },
      pages: { type: Number, default: 1 },
      total: { type: Number, default: 0 },
      size: { type: Number, default: 20 },
    },
    emits: ['update:page', 'update:size'],
    computed: {
      numbers: function () { return App.pageNumbers(this.page, Math.max(this.pages, 1)); },
    },
    methods: {
      go: function (p) {
        if (p === '...' || p === this.page || p < 1 || p > this.pages) return;
        this.$emit('update:page', p);
      },
    },
    template: `
      <div class="pager">
        <span>共 <b>{{ total }}</b> 条记录，第 {{ page }} / {{ Math.max(pages, 1) }} 页</span>
        <select :value="size" @change="$emit('update:size', Number($event.target.value))"
                style="width:auto;padding:4px 8px">
          <option :value="10">10 条/页</option>
          <option :value="20">20 条/页</option>
          <option :value="50">50 条/页</option>
          <option :value="100">100 条/页</option>
        </select>
        <div class="pages">
          <button class="pg" :disabled="page <= 1" @click="go(page - 1)">‹</button>
          <button v-for="(p, i) in numbers" :key="i" class="pg"
                  :class="{ active: p === page }"
                  :disabled="p === '...'"
                  @click="go(p)">{{ p }}</button>
          <button class="pg" :disabled="page >= pages" @click="go(page + 1)">›</button>
        </div>
      </div>`,
  };

  /* ------------------------------------------------------------ 弹窗 */
  Components.Modal = {
    props: {
      title: { type: String, default: '' },
      size: { type: String, default: '' },        // wide / narrow / ''
      loading: { type: Boolean, default: false },
      okText: { type: String, default: '保存' },
      cancelText: { type: String, default: '取消' },
      hideFooter: { type: Boolean, default: false },
    },
    emits: ['close', 'ok'],
    mounted: function () {
      this._esc = (e) => { if (e.key === 'Escape') this.$emit('close'); };
      document.addEventListener('keydown', this._esc);
    },
    unmounted: function () { document.removeEventListener('keydown', this._esc); },
    methods: {
      onOverlay: function (e) { if (e.target === e.currentTarget) this.$emit('close'); },
    },
    template: `
      <div class="overlay" @mousedown="onOverlay">
        <div class="modal" :class="size">
          <div class="modal-head">
            <h3>{{ title }}</h3>
            <button class="close" @click="$emit('close')" title="关闭">×</button>
          </div>
          <div class="modal-body"><slot></slot></div>
          <div class="modal-foot" v-if="!hideFooter">
            <div class="left"><slot name="foot-left"></slot></div>
            <button class="btn" @click="$emit('close')" :disabled="loading">{{ cancelText }}</button>
            <button class="btn primary" @click="$emit('ok')" :disabled="loading">
              {{ loading ? '处理中 ...' : okText }}
            </button>
          </div>
        </div>
      </div>`,
  };

  /* ------------------------------------------------------------ 空状态 */
  Components.EmptyState = {
    props: {
      icon: { type: String, default: '📭' },
      text: { type: String, default: '暂无数据' },
      hint: { type: String, default: '' },
    },
    template: `
      <div class="empty">
        <div class="icon">{{ icon }}</div>
        <p>{{ text }}</p>
        <p v-if="hint" class="fs12 text-light mt1">{{ hint }}</p>
        <div class="mt2"><slot></slot></div>
      </div>`,
  };

  /* ------------------------------------------------------------ 加载中 */
  Components.Loading = {
    props: { text: { type: String, default: '加载中 ...' } },
    template: `
      <div class="empty">
        <div class="boot-spinner" style="margin:0 auto 12px"></div>
        <p>{{ text }}</p>
      </div>`,
  };

  /* ------------------------------------------------------------ 进度条 */
  Components.ProgressBar = {
    props: {
      value: { type: Number, default: 0 },
      status: { type: String, default: '' },
      showText: { type: Boolean, default: true },
    },
    computed: {
      cls: function () { return 'bar ' + App.progressClass(this.value, this.status); },
      pct: function () { return App.clamp(this.value, 0, 100); },
    },
    template: `
      <div class="flex-center gap1">
        <div :class="cls" style="flex:1"><i :style="{ width: pct + '%' }"></i></div>
        <span class="progress-mini" v-if="showText" style="width:34px;text-align:right">{{ pct }}%</span>
      </div>`,
  };

  /* ------------------------------------------------------------ 部门选择器 */
  Components.DeptSelect = {
    props: {
      modelValue: { type: [Number, String, null], default: null },
      depts: { type: Array, default: function () { return []; } },
      placeholder: { type: String, default: '全部部门' },
      allowEmpty: { type: Boolean, default: true },
    },
    emits: ['update:modelValue'],
    computed: {
      // 缩进展示层级，让用户看清上下级关系
      options: function () {
        const byParent = {};
        this.depts.forEach(function (d) { (byParent[d.parent_id || 0] = byParent[d.parent_id || 0] || []).push(d); });
        const out = [];
        const walk = function (pid, depth) {
          (byParent[pid] || []).forEach(function (d) {
            out.push({ id: d.id, label: '　'.repeat(depth) + d.name, depth: depth });
            walk(d.id, depth + 1);
          });
        };
        walk(0, 0);
        // 父部门不可见时可能出现游离节点，一并补上
        if (out.length < this.depts.length) {
          const seen = {};
          out.forEach(function (o) { seen[o.id] = true; });
          this.depts.forEach(function (d) { if (!seen[d.id]) out.push({ id: d.id, label: d.name, depth: 0 }); });
        }
        return out;
      },
    },
    template: `
      <select :value="modelValue === null ? '' : modelValue"
              @change="$emit('update:modelValue', $event.target.value === '' ? null : Number($event.target.value))">
        <option v-if="allowEmpty" value="">{{ placeholder }}</option>
        <option v-for="o in options" :key="o.id" :value="o.id">{{ o.label }}</option>
      </select>`,
  };

  /* ------------------------------------------------------------ 公告正文渲染 */
  Components.AnnouncementBody = {
    props: { content: { type: String, default: '' } },
    computed: {
      html: function () {
        // 纯文本按段落渲染，转义后再处理换行，避免 XSS
        const safe = String(this.content || '')
          .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        return safe.split(/\n/).map(function (line) {
          return line.trim() ? '<p style="margin:0 0 8px;line-height:1.85">' + line + '</p>' : '';
        }).join('');
      },
    },
    template: '<div v-html="html"></div>',
  };

  /* ------------------------------------------------------------ 详情行 */
  Components.InfoRow = {
    props: { label: String, value: [String, Number], full: Boolean },
    template: `
      <div class="row" :class="{ full: full }">
        <div class="k">{{ label }}</div>
        <div class="v"><slot>{{ value === null || value === undefined || value === '' ? '—' : value }}</slot></div>
      </div>`,
  };

  window.Components = Components;
})();
