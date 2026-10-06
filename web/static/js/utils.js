/* ==========================================================================
   通用工具：提示、确认框、格式化、状态徽标
   全局对象 App 同时承担跨组件通信（toast / confirm / 当前用户）
   ========================================================================== */
(function () {
  'use strict';

  /*
    当前登录用户放在一个「响应式」容器里，两个原因：
      1) 登录成功后顶栏要立刻变成真实姓名/角色，不能等刷新页面；
      2) 之前踩过的坑：组件里写 `data() { return { user: App.user } }` 只是按值拷贝了
         当时的对象，而登录是 `App.user = res.user`（换了个新对象），
         于是顶栏一直停在旧值上，表现为"明明登录了却显示未登录"。
    所以用户信息统一存在这里，读写都走 App.user / App.setUser()，
    组件里用 computed 引用 App.state.user，任何一处更新全场自动同步。
  */
  const state = Vue.reactive({
    user: null,      // 当前登录用户（/api/me 返回的对象）
    booted: false,   // 是否已经尝试过恢复登录态，用于避免重复请求
  });

  const App = {
    state: state,
    currentYear: new Date().getFullYear(),

    /* ---------------------------------------------------------- 当前用户 */
    get user() { return state.user; },
    set user(value) { state.user = value; },

    /** 统一入口：同时更新内存状态与本地缓存，保证刷新后不丢 */
    setUser: function (user) {
      state.user = user;
      API.store.user = user;
    },

    /** 彻底清空登录信息（退出登录 / 令牌失效） */
    clearUser: function () {
      state.user = null;
      API.store.clear();
    },

    /* ---------------------------------------------------------- 提示条 */
    toast: function (message, type) {
      type = type || 'info';
      const host = document.getElementById('toast-host');
      if (!host) { console.log('[toast]', message); return; }
      const el = document.createElement('div');
      el.className = 'toast ' + type;
      const icon = { success: '✅', error: '⛔', warning: '⚠️', info: 'ℹ️' }[type] || 'ℹ️';
      el.textContent = icon + ' ' + message;
      host.appendChild(el);
      setTimeout(function () {
        el.style.transition = 'opacity .25s, transform .25s';
        el.style.opacity = '0';
        el.style.transform = 'translateY(-10px)';
        setTimeout(function () { el.remove(); }, 260);
      }, type === 'error' ? 4200 : 2600);
    },

    /* ---------------------------------------------------------- 确认框 */
    _confirm: null,      // 由 app.js 注入实际的弹窗实现

    confirm: function (options) {
      // 允许直接传字符串
      if (typeof options === 'string') options = { message: options };
      const opts = Object.assign({
        title: '请确认',
        message: '',
        detail: '',
        okText: '确定',
        cancelText: '取消',
        danger: false,
      }, options || {});

      if (!App._confirm) {
        // 兜底：极端情况下用原生 confirm，保证功能不丢
        return Promise.resolve(window.confirm(opts.message));
      }
      return App._confirm(opts);
    },

    /* ---------------------------------------------------------- 角色 */
    role: function () { return (App.user && App.user.role) || 'employee'; },
    /** 是否最高权限角色（老板 / 系统管理员）—— 与后端 ADMIN_LIKE_ROLES 保持一致 */
    isAdmin: function () { return App.role() === 'admin' || App.role() === 'boss'; },
    isBoss: function () { return App.role() === 'boss'; },
    isManager: function () { return App.isAdmin() || App.role() === 'manager'; },
    roleLabel: function (role) {
      return {
        boss: '老板',
        admin: '系统管理员',
        manager: '部门主管',
        employee: '普通员工',
      }[role || App.role()] || '—';
    },

    /* ---------------------------------------------------------- 格式化 */
    pad: function (n) { return n < 10 ? '0' + n : '' + n; },

    /** 今天，YYYY-MM-DD */
    today: function () {
      const d = new Date();
      return d.getFullYear() + '-' + App.pad(d.getMonth() + 1) + '-' + App.pad(d.getDate());
    },

    /** 本月，YYYY-MM */
    thisMonth: function () {
      const d = new Date();
      return d.getFullYear() + '-' + App.pad(d.getMonth() + 1);
    },

    /** N 天后的日期，YYYY-MM-DD */
    dateAfter: function (days) {
      const d = new Date();
      d.setDate(d.getDate() + days);
      return d.getFullYear() + '-' + App.pad(d.getMonth() + 1) + '-' + App.pad(d.getDate());
    },

    /** 只保留日期部分 */
    dateOnly: function (value) {
      if (!value) return '—';
      return String(value).slice(0, 10);
    },

    /** 日期 + 时间，截断到分钟 */
    dateTime: function (value) {
      if (!value) return '—';
      return String(value).replace('T', ' ').slice(0, 16);
    },

    /** 相对时间：3 分钟前 / 2 天前 */
    fromNow: function (value) {
      if (!value) return '—';
      const t = new Date(String(value).replace(' ', 'T'));
      if (isNaN(t.getTime())) return String(value).slice(0, 16);
      const diff = (Date.now() - t.getTime()) / 1000;
      if (diff < 60) return '刚刚';
      if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
      if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
      if (diff < 86400 * 30) return Math.floor(diff / 86400) + ' 天前';
      return App.dateOnly(value);
    },

    /** 文件大小 */
    fileSize: function (bytes) {
      if (!bytes && bytes !== 0) return '—';
      let n = Number(bytes);
      const units = ['B', 'KB', 'MB', 'GB'];
      let i = 0;
      while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
      return (i === 0 ? n.toFixed(0) : n.toFixed(1)) + ' ' + units[i];
    },

    /** 金额，千分位 */
    money: function (value) {
      if (value === null || value === undefined || value === '') return '—';
      return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 });
    },

    /** 数字兜底 */
    num: function (value, fallback) {
      const n = Number(value);
      return isNaN(n) ? (fallback === undefined ? 0 : fallback) : n;
    },

    /** 取姓名首字（头像占位） */
    initials: function (name) {
      if (!name) return '?';
      return String(name).trim().slice(0, 1).toUpperCase();
    },

    /** 头像地址 */
    avatarUrl: function (user) {
      if (!user || !user.avatar) return '';
      return user.avatar.indexOf('http') === 0 ? user.avatar : user.avatar;
    },

    /* ---------------------------------------------------------- 状态 -> 徽标颜色 */
    statusClass: function (status) {
      const map = {
        // 员工
        '在职': 'green', '试用期': 'blue', '休假': 'yellow', '离职': 'gray',
        // 项目
        '筹备中': 'blue', '进行中': 'green', '已暂停': 'yellow', '已完成': 'gray', '已归档': 'gray',
        // 优先级
        '低': 'gray', '中': 'blue', '高': 'yellow', '紧急': 'red',
        // 考勤
        '正常': 'green', '迟到': 'yellow', '早退': 'yellow', '缺卡': 'red', '旷工': 'red',
        '请假': 'blue', '出差': 'purple',
        // 审批
        '待审批': 'yellow', '已通过': 'green', '已驳回': 'red', '已撤销': 'gray',
        // 账号
        '启用': 'green', '停用': 'gray',
      };
      return map[status] || 'gray';
    },

    /** 进度条颜色 */
    progressClass: function (progress, status) {
      if (status === '已完成' || status === '已归档') return 'green';
      const p = App.num(progress);
      if (p >= 80) return 'green';
      if (p >= 40) return '';
      return 'yellow';
    },

    /** 根据目标位置生成一个渐变头像底色 */
    avatarColor: function (name) {
      const palette = ['#2b6cb0', '#2f855a', '#b7791f', '#805ad5', '#c53030', '#2c7a7b', '#4c51bf'];
      let sum = 0;
      String(name || '?').split('').forEach(function (ch) { sum += ch.charCodeAt(0); });
      return palette[sum % palette.length];
    },

    /* ---------------------------------------------------------- 杂项 */
    /** 把秒数转成 YYYY-MM-DD */
    isoDay: function (dateObj) {
      return dateObj.getFullYear() + '-' + App.pad(dateObj.getMonth() + 1) + '-' + App.pad(dateObj.getDate());
    },

    /** 数值限制在范围内 */
    clamp: function (value, min, max) {
      return Math.min(Math.max(App.num(value), min), max);
    },

    /** 把逗号/空格分隔的标签转成数组 */
    tagList: function (tags) {
      if (!tags) return [];
      return String(tags).split(/[,，\s]+/).filter(function (t) { return t; });
    },

    /** 生成页码按钮序列，超过 7 页时用省略号 */
    pageNumbers: function (current, total) {
      const list = [];
      if (total <= 7) {
        for (let i = 1; i <= total; i++) list.push(i);
        return list;
      }
      list.push(1);
      let start = Math.max(2, current - 1);
      let end = Math.min(total - 1, current + 1);
      if (start > 2) list.push('...');
      for (let i = start; i <= end; i++) list.push(i);
      if (end < total - 1) list.push('...');
      list.push(total);
      return list;
    },

    /** 复制文本到剪贴板 */
    copy: function (text) {
      if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function () { App.toast('已复制到剪贴板', 'success'); });
      } else {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
        App.toast('已复制到剪贴板', 'success');
      }
    },
  };

  window.App = App;
})();
