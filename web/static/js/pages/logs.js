/* ==========================================================================
   操作日志（审计）：统计图表 + 明细查询
   ========================================================================== */
(function () {
  'use strict';

  window.PageLogs = {
    data: function () {
      return {
        tab: 'all',                     // all（管理员）/ mine（所有人）
        loading: false,
        rows: [], total: 0, page: 1, size: 30, pages: 1,
        query: { keyword: '', module: '', action: '', date_from: '', date_to: '' },
        modules: [], actions: [],
        stats: null, statsDays: 7,
        chartLoading: false,
      };
    },
    computed: {
      isAdmin: function () { return App.isAdmin(); },
    },
    mounted: function () {
      this.tab = this.isAdmin ? 'all' : 'mine';
      this.load();
      if (this.isAdmin) this.loadStats();
    },
    methods: {
      load: async function () {
        this.loading = true;
        try {
          const params = Object.assign({ page: this.page, size: this.size }, this.query);
          const res = this.tab === 'all'
            ? await API.logs.list(params)
            : await API.logs.mine({ page: this.page, size: this.size });
          this.rows = res.items;
          this.total = res.total;
          this.pages = res.pages;
          if (res.modules) this.modules = res.modules;
          if (res.actions) this.actions = res.actions;
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.loading = false; }
      },
      loadStats: async function () {
        if (!this.isAdmin) return;
        this.chartLoading = true;
        try {
          this.stats = await API.logs.stats(this.statsDays);
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.chartLoading = false; }
      },
      switchTab: function (t) { this.tab = t; this.page = 1; this.load(); },
      search: function () { this.page = 1; this.load(); },
      reset: function () {
        this.query = { keyword: '', module: '', action: '', date_from: '', date_to: '' };
        this.search();
      },
      changePage: function (p) { this.page = p; this.load(); },
      changeSize: function (s) { this.size = s; this.page = 1; this.load(); },
      refresh: function () { this.load(); if (this.isAdmin) this.loadStats(); },

      actionClass: function (action) { return App.statusClass(action); },
      fromNow: function (v) { return App.fromNow(v); },
      fmt: function (v) { return App.dateTime(v); },
    },
    template: `
      <div>
        <!-- ================= 统计图表（仅管理员） ================= -->
        <template v-if="isAdmin">
          <div class="card">
            <div class="card-head">
              <h3>操作统计</h3>
              <span class="sub">用于排查"谁在什么时候动了什么数据"</span>
              <select v-model.number="statsDays" @change="loadStats" style="width:auto">
                <option :value="1">最近 1 天</option>
                <option :value="7">最近 7 天</option>
                <option :value="30">最近 30 天</option>
                <option :value="90">最近 90 天</option>
              </select>
            </div>
            <div class="card-body">
              <loading v-if="chartLoading"></loading>
              <template v-else-if="stats">
                <div class="grid c4 mb2">
                  <stat-card label="操作总数" :value="stats.total"
                             :foot="'最近 ' + stats.days + ' 天'" accent="1" icon="🗂️"></stat-card>
                  <stat-card label="涉及模块" :value="Object.keys(stats.by_module).length"
                             foot="有操作记录的模块" accent="4" icon="📦"></stat-card>
                  <stat-card label="活跃账号" :value="Object.keys(stats.by_user).length"
                             foot="产生过操作的账号数" accent="2" icon="👤"></stat-card>
                  <stat-card label="日均操作"
                             :value="stats.days ? Math.round(stats.total / stats.days) : 0"
                             foot="平均每天的操作次数" accent="3" icon="📈"></stat-card>
                </div>
                <div class="grid c3">
                  <div>
                    <div class="fs13 text-muted mb1">各模块操作次数</div>
                    <h-bar-chart :data="stats.by_module" height="230px"></h-bar-chart>
                  </div>
                  <div>
                    <div class="fs13 text-muted mb1">操作类型分布</div>
                    <pie-chart :data="stats.by_action" height="230px"></pie-chart>
                  </div>
                  <div>
                    <div class="fs13 text-muted mb1">每日操作趋势</div>
                    <line-chart :data="stats.by_day" height="230px"></line-chart>
                  </div>
                </div>
                <div class="mt2">
                  <div class="fs13 text-muted mb1">操作最活跃的账号</div>
                  <div class="flex-center gap2 wrap">
                    <span v-for="(count, name) in stats.by_user" :key="name" class="tag blue">
                      {{ name }}：{{ count }} 次
                    </span>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </template>

        <!-- ================= 日志明细 ================= -->
        <div class="card">
          <div class="tabs">
            <div class="tab" v-if="isAdmin" :class="{ active: tab === 'all' }" @click="switchTab('all')">
              全部操作日志
            </div>
            <div class="tab" :class="{ active: tab === 'mine' }" @click="switchTab('mine')">
              我的操作记录
            </div>
          </div>

          <div class="filters" v-if="tab === 'all'">
            <input class="grow" type="text" v-model="query.keyword" @keyup.enter="search"
                   placeholder="搜索操作详情或操作人 ...">
            <select v-model="query.module" @change="search">
              <option value="">全部模块</option>
              <option v-for="m in modules" :key="m" :value="m">{{ m }}</option>
            </select>
            <select v-model="query.action" @change="search">
              <option value="">全部操作类型</option>
              <option v-for="a in actions" :key="a" :value="a">{{ a }}</option>
            </select>
            <input type="date" v-model="query.date_from" @change="search" title="起始日期">
            <span class="text-light">~</span>
            <input type="date" v-model="query.date_to" @change="search" title="结束日期">
            <button class="btn primary" @click="search">🔍 查询</button>
            <button class="btn" @click="reset">重置</button>
            <div class="spacer"></div>
            <button class="btn" @click="refresh">🔄 刷新</button>
          </div>
          <div class="filters" v-else>
            <span class="fs13 text-muted">这里只显示你自己的操作记录，用于核对个人操作历史。</span>
            <div class="spacer"></div>
            <button class="btn" @click="refresh">🔄 刷新</button>
          </div>

          <div class="card-body tight">
            <loading v-if="loading"></loading>
            <empty-state v-else-if="!rows.length" icon="🗂️" text="没有符合条件的操作日志"></empty-state>
            <div class="table-wrap" v-else>
              <table class="data">
                <thead>
                  <tr>
                    <th style="width:150px">时间</th>
                    <th style="width:110px">操作人</th>
                    <th style="width:90px">类型</th>
                    <th style="width:110px">模块</th>
                    <th>操作详情</th>
                    <th style="width:120px">来源 IP</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in rows" :key="r.id">
                    <td class="fs12 nowrap">
                      <div>{{ fmt(r.created_at) }}</div>
                      <div class="text-light">{{ fromNow(r.created_at) }}</div>
                    </td>
                    <td class="strong">{{ r.username || '系统' }}</td>
                    <td><span class="tag" :class="actionClass(r.action)">{{ r.action }}</span></td>
                    <td class="fs12">{{ r.module }}</td>
                    <td class="fs13">{{ r.detail || '—' }}</td>
                    <td class="mono fs12 text-muted">{{ r.ip || '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <pagination v-if="!loading && rows.length" :page="page" :pages="pages" :total="total"
                      :size="size" @update:page="changePage" @update:size="changeSize"></pagination>
        </div>
      </div>`,
  };
})();
