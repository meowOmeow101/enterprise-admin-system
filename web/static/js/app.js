/* ==========================================================================
   应用入口：路由、布局、导航守卫
   ========================================================================== */
(function () {
  'use strict';

  const { createApp, ref, computed, reactive } = Vue;
  const { createRouter, createWebHashHistory } = VueRouter;

  /* ------------------------------------------------------------ 路由表 */
  /**
   * 惰性取页面组件。
   *
   * 这里刻意不写成 component: window.PageXxx —— 那样会在脚本执行到本行时立即求值，
   * 一旦页面脚本的加载顺序有变化（曾经就因此让 /login 变成"没有组件的路由"，
   * 表现是登录页整页空白），就会埋下很难查的坑。
   * 改成函数后，Vue Router 在真正渲染该路由时才求值，顺序问题自然消失。
   *
   * 注意：Vue Router 4 会把异步组件函数当作"返回 Promise 的工厂"，
   * 直接返回组件对象会报 "r.then is not a function"，所以必须包成 Promise。
   */
  function page(name) {
    return function () {
      const component = window[name];
      if (!component) {
        console.error('[路由] 页面组件未加载：' + name);
        return Promise.resolve({
          template: '<div class="empty"><div class="icon">⚠️</div>' +
            '<p>页面组件 ' + name + ' 未能加载，请刷新页面重试</p></div>',
        });
      }
      return Promise.resolve(component);
    };
  }

  const routes = [
    { path: '/login', name: 'login', component: page('PageLogin'),
      meta: { public: true, title: '登录' } },
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', name: 'dashboard', component: page('PageDashboard'),
      meta: { title: '数据看板', crumb: '工作台' } },
    { path: '/projects', name: 'projects', component: page('PageProjects'),
      meta: { title: '项目管理', crumb: '工作台' } },
    { path: '/reports', name: 'reports', component: page('PageReports'),
      meta: { title: '报告管理', crumb: '工作台' } },
    { path: '/employees', name: 'employees', component: page('PageEmployees'),
      meta: { title: '员工管理', crumb: '组织人事' } },
    { path: '/departments', name: 'departments', component: page('PageDepartments'),
      meta: { title: '部门架构', crumb: '组织人事' } },
    { path: '/attendance', name: 'attendance', component: page('PageAttendance'),
      meta: { title: '考勤打卡', crumb: '审批与考勤' } },
    { path: '/leaves', name: 'leaves', component: page('PageLeaves'),
      meta: { title: '请假审批', crumb: '审批与考勤' } },
    { path: '/announcements', name: 'announcements', component: page('PageAnnouncements'),
      meta: { title: '公告通知', crumb: '公司信息' } },
    { path: '/profile', name: 'profile', component: page('PageProfile'),
      meta: { title: '个人中心', crumb: '公司信息' } },
    { path: '/accounts', name: 'accounts', component: page('PageAccounts'),
      meta: { title: '账号管理', crumb: '系统管理', roles: ['admin', 'boss'] } },
    { path: '/logs', name: 'logs', component: page('PageLogs'),
      meta: { title: '操作日志', crumb: '系统管理', roles: ['admin', 'boss'] } },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ];

  const router = createRouter({ history: createWebHashHistory(), routes });

  /* ------------------------------------------------------------ 菜单结构 */
  const MENU = [
    {
      group: '工作台', items: [
        { path: '/dashboard', label: '数据看板', icon: '📊' },
        { path: '/projects', label: '项目管理', icon: '📁' },
        { path: '/reports', label: '报告管理', icon: '📄' },
      ],
    },
    {
      group: '组织人事', items: [
        { path: '/employees', label: '员工管理', icon: '👥' },
        { path: '/departments', label: '部门架构', icon: '🏢' },
      ],
    },
    {
      group: '审批与考勤', items: [
        { path: '/attendance', label: '考勤打卡', icon: '🕘' },
        { path: '/leaves', label: '请假审批', icon: '📝', badge: 'pendingLeaves' },
      ],
    },
    {
      group: '公司信息', items: [
        { path: '/announcements', label: '公告通知', icon: '📢', badge: 'unreadAnn' },
        { path: '/profile', label: '个人中心', icon: '👤' },
      ],
    },
    {
      group: '系统管理', roles: ['admin', 'boss'], items: [
        { path: '/accounts', label: '账号管理', icon: '🔑' },
        { path: '/logs', label: '操作日志', icon: '🗂️' },
      ],
    },
  ];

  /* ------------------------------------------------------------ 确认弹窗（全局单例） */
  const ConfirmDialog = {
    data: function () {
      return { visible: false, opts: {}, resolver: null };
    },
    mounted: function () {
      const self = this;
      // 把实现注入到 App.confirm，页面里就能直接 await App.confirm(...)
      App._confirm = function (options) {
        self.opts = options;
        self.visible = true;
        return new Promise(function (resolve) { self.resolver = resolve; });
      };
    },
    methods: {
      finish: function (result) {
        this.visible = false;
        if (this.resolver) this.resolver(result);
        this.resolver = null;
      },
    },
    template: `
      <div class="overlay" v-if="visible" @mousedown.self="finish(false)" style="z-index:300">
        <div class="modal narrow">
          <div class="modal-head"><h3>{{ opts.title }}</h3></div>
          <div class="modal-body">
            <p style="margin:0;line-height:1.75">{{ opts.message }}</p>
            <p v-if="opts.detail" class="fs12 text-muted mt1" style="line-height:1.7">{{ opts.detail }}</p>
          </div>
          <div class="modal-foot">
            <button class="btn" @click="finish(false)">{{ opts.cancelText }}</button>
            <button class="btn" :class="opts.danger ? 'danger' : 'primary'" @click="finish(true)">
              {{ opts.okText }}
            </button>
          </div>
        </div>
      </div>`,
  };

  /* ------------------------------------------------------------ 登录页 */
  window.PageLogin = {
    data: function () {
      return {
        username: '', password: '', loading: false, error: '',
        demos: [
          { u: 'boss', n: '王建国', d: '老板 · 全部权限' },
          { u: 'admin', n: '赵敏', d: '系统管理员 · 全部权限' },
          { u: 'liqiang', n: '李强', d: '技术部主管 · 本部门及下级' },
          { u: 'yanglei', n: '杨磊', d: '普通员工 · 仅本人相关' },
        ],
      };
    },
    mounted: function () { this.$refs.u && this.$refs.u.focus(); },
    methods: {
      pick: function (d) { this.username = d.u; this.password = '123456'; this.error = ''; },
      submit: async function () {
        if (!this.username || !this.password) { this.error = '请填写用户名和密码'; return; }
        this.loading = true;
        this.error = '';
        try {
          const res = await API.auth.login(this.username.trim(), this.password);
          API.store.token = res.token;
          App.setUser(res.user);          // 写入响应式状态，顶栏立即刷新
          App.state.booted = true;
          App.toast('欢迎回来，' + res.user.real_name, 'success');
          const redirect = sessionStorage.getItem('cadmin.redirect') || '/dashboard';
          sessionStorage.removeItem('cadmin.redirect');
          this.$router.replace(redirect);
        } catch (e) {
          this.error = e.message || '登录失败';
        } finally {
          this.loading = false;
        }
      },
    },
    template: `
      <div class="login-page">
        <div class="login-card">
          <div class="brand">
            <div class="logo">🏢</div>
            <h2>企业后台管理系统</h2>
            <p>员工 · 项目 · 报告 · 考勤一体化管理</p>
          </div>

          <div class="login-error" v-if="error">{{ error }}</div>

          <form @submit.prevent="submit">
            <div class="form-item">
              <label>用户名</label>
              <input ref="u" type="text" v-model="username" placeholder="请输入用户名" autocomplete="username">
            </div>
            <div class="form-item">
              <label>密码</label>
              <input type="password" v-model="password" placeholder="请输入密码" autocomplete="current-password">
            </div>
            <button class="btn primary block" type="submit" :disabled="loading">
              {{ loading ? '登录中 ...' : '登 录' }}
            </button>
          </form>

          <div class="demo-accounts">
            <div class="mb1"><b>演示账号</b>（点击自动填充，密码均为 123456）</div>
            <div class="row" v-for="d in demos" :key="d.u" @click="pick(d)">
              <span><b>{{ d.u }}</b> · {{ d.n }}</span>
              <span>{{ d.d }}</span>
            </div>
          </div>
        </div>
      </div>`,
  };

  /* ------------------------------------------------------------ 根组件 */
  const RootApp = {
    components: { ConfirmDialog: ConfirmDialog },
    data: function () {
      return {
        menu: MENU,
        collapsed: false,
        showUserMenu: false,
        badges: { pendingLeaves: 0, unreadAnn: 0 },
      };
    },
    computed: {
      // 注意：必须走 computed 读响应式状态，不能在 data() 里按值拷贝 App.user
      // （否则登录后顶栏不会更新，会一直显示"未登录"）
      user: function () { return App.state.user; },
      routeTitle: function () { return (this.$route.meta && this.$route.meta.title) || '数据看板'; },
      routeCrumb: function () { return (this.$route.meta && this.$route.meta.crumb) || ''; },
      isLoginPage: function () { return this.$route.name === 'login'; },
      visibleMenu: function () {
        const role = this.user ? this.user.role : 'employee';
        return this.menu.filter(function (g) { return !g.roles || g.roles.indexOf(role) >= 0; })
          .map(function (g) {
            return Object.assign({}, g, {
              items: g.items.filter(function (it) { return !it.roles || it.roles.indexOf(role) >= 0; }),
            });
          }).filter(function (g) { return g.items.length > 0; });
      },
      roleText: function () { return App.roleLabel(this.user && this.user.role); },
      deptText: function () { return (this.user && this.user.department_name) || '未分配部门'; },
    },
    mounted: function () {
      const self = this;
      // 点击空白处收起用户菜单
      document.addEventListener('click', function (e) {
        if (!e.target.closest || !e.target.closest('.user-box')) self.showUserMenu = false;
      });
      this.$router.afterEach(function () { self.loadBadges(); });
      this.loadBadges();
      setInterval(function () { self.loadBadges(); }, 120000);   // 每两分钟刷新待办角标
    },
    methods: {
      badgeOf: function (key) { return this.badges[key] || 0; },
      isActive: function (path) { return this.$route.path === path; },
      loadBadges: async function () {
        if (!API.store.token) return;
        try {
          const data = await API.dashboard.overview();
          this.badges.pendingLeaves = data.leaves.my_pending + (App.isManager() ? data.leaves.pending_total : 0);
          this.badges.unreadAnn = (data.announcements || []).filter(function (a) { return !a.is_read; }).length;
        } catch (e) { /* 角标失败不影响主流程 */ }
      },
      go: function (path) { this.$router.push(path); },
      logout: async function () {
        const ok = await App.confirm({ title: '退出登录', message: '确定要退出当前账号吗？' });
        if (!ok) return;
        App.clearUser();
        App.toast('已安全退出', 'success');
        this.$router.replace('/login');
      },
      reload: function () { window.location.reload(); },
      setUser: function (u) { App.setUser(u); },
    },
    provide: function () {
      const self = this;
      return {
        // 页面可以通过 inject('setUser') 更新顶部用户信息（个人中心改姓名时用到）
        setUser: function (u) { self.setUser(u); },
        refreshBadges: function () { self.loadBadges(); },
      };
    },
    template: `
      <div>
        <!-- 登录页单独渲染，不套后台框架 -->
        <router-view v-if="isLoginPage"></router-view>

        <div class="layout" v-else>
          <aside class="sidebar">
            <div class="sidebar-brand">
              <div class="logo">🏢</div>
              <span class="brand-text">企业后台管理</span>
            </div>
            <nav class="sidebar-nav">
              <template v-for="g in visibleMenu" :key="g.group">
                <div class="nav-group-label">{{ g.group }}</div>
                <div v-for="it in g.items" :key="it.path" class="nav-item"
                     :class="{ active: isActive(it.path) }" @click="go(it.path)">
                  <span class="ico">{{ it.icon }}</span>
                  <span class="label">{{ it.label }}</span>
                  <span class="badge-dot" v-if="it.badge && badgeOf(it.badge) > 0">{{ badgeOf(it.badge) }}</span>
                </div>
              </template>
            </nav>
          </aside>

          <div class="main">
            <header class="topbar">
              <h1>{{ routeTitle }}<span class="crumb" v-if="routeCrumb">/ {{ routeCrumb }}</span></h1>
              <button class="btn sm" @click="reload" title="刷新页面">🔄 刷新</button>
              <div class="user-box" @click="showUserMenu = !showUserMenu">
                <img v-if="user && user.avatar" class="avatar" :src="user.avatar" alt="">
                <div v-else class="avatar" :style="{ background: App.avatarColor(user && user.real_name) }">
                  {{ App.initials(user && user.real_name) }}
                </div>
                <div class="meta">
                  <b>{{ user ? user.real_name : '未登录' }}
                    <span class="tag purple" v-if="user && user.role === 'boss'"
                          style="margin-left:4px">👑 老板</span>
                  </b>
                  <span>{{ roleText }} · {{ deptText }}</span>
                </div>
                <span class="text-light" style="font-size:11px">▾</span>

                <div class="dropdown" v-if="showUserMenu" @click.stop>
                  <div class="dropdown-item" @click="go('/profile')">👤 个人中心</div>
                  <div class="dropdown-item" @click="go('/attendance')">🕘 我的考勤</div>
                  <div class="dropdown-item" @click="go('/announcements')">📢 公告通知</div>
                  <div class="dropdown-divider"></div>
                  <div class="dropdown-item danger" @click="logout">🚪 退出登录</div>
                </div>
              </div>
            </header>

            <main class="content">
              <router-view :key="$route.fullPath"></router-view>
            </main>
          </div>
        </div>

        <confirm-dialog></confirm-dialog>
      </div>`,
  };

  /* ------------------------------------------------------------ 导航守卫 */
  router.beforeEach(function (to) {
    const logged = !!API.store.token;
    if (to.meta && to.meta.public) {
      if (logged && to.name === 'login') return '/dashboard';
      return true;
    }
    if (!logged) {
      sessionStorage.setItem('cadmin.redirect', to.fullPath);
      return '/login';
    }
    // 恢复登录态：优先用本地缓存的用户信息，没有就向服务端要一次。
    // 不管走哪条路，最终都通过 App.setUser 写进响应式状态，
    // 这样顶栏在有缓存时也能立刻显示姓名，不必等接口返回。
    if (!App.user) {
      const cached = API.store.user;
      if (cached) App.setUser(cached);
      else return API.auth.me()
        .then(function (u) { App.setUser(u); return true; })
        .catch(function () { return '/login'; });
    }
    const role = App.role();
    if (to.meta && to.meta.roles && to.meta.roles.indexOf(role) < 0) {
      App.toast('权限不足，无法访问该页面', 'error');
      return '/dashboard';
    }
    return true;
  });

  // 路由异常直接提示出来，避免出现"点了菜单页面空白但没人知道为什么"
  router.onError(function (err) {
    console.error('[路由异常]', err);
    App.toast('页面加载失败：' + ((err && err.message) || err), 'error');
  });

  /* ------------------------------------------------------------ 启动 */
  const app = createApp(RootApp);
  app.component('confirm-dialog', ConfirmDialog);

  // 注册全局组件
  Object.keys(window.Components).forEach(function (name) {
    app.component(name, window.Components[name]);
  });
  // 注册图表组件
  ['PieChart', 'BarChart', 'LineChart', 'HBarChart'].forEach(function (name) {
    if (window.Charts[name]) app.component(name, window.Charts[name]);
  });

  app.config.globalProperties.App = App;
  app.config.globalProperties.API = API;

  // 兜底：把未捕获的接口错误统一提示出来
  app.config.errorHandler = function (err) {
    console.error(err);
    if (typeof window.__cadminLogRoute === 'function') {
      window.__cadminLogRoute('组件渲染错误 ' + ((err && err.message) || err));
    }
    App.toast((err && err.message) || '页面发生错误', 'error');
  };

  app.use(router);
  app.mount('#app');

  // 通知自测脚本：Vue 已成功挂载
  if (typeof window.__cadminMarkMounted === 'function') window.__cadminMarkMounted();
})();
