/* ==========================================================================
   项目管理：卡片/列表双视图、进度更新、成员维护
   ========================================================================== */
(function () {
  'use strict';

  const EMPTY_FORM = function () {
    return {
      id: null, code: '', name: '', description: '', customer: '', status: '进行中',
      priority: '中', progress: 0, department_id: null, owner_id: null,
      start_date: App.today(), end_date: '', budget: '',
    };
  };

  window.PageProjects = {
    data: function () {
      return {
        loading: true,
        rows: [], total: 0, page: 1, size: 12, pages: 1,
        view: 'card',                 // card / table
        depts: [], employees: [],
        query: { keyword: '', status: '', priority: '', department_id: null, mine: false },
        stats: null,
        statusList: ['筹备中', '进行中', '已暂停', '已完成', '已归档'],
        priorityList: ['低', '中', '高', '紧急'],
        // 弹窗
        showForm: false, saving: false, form: EMPTY_FORM(),
        showDetail: false, detail: null,
        showMember: false, memberPick: [], memberRole: '开发', savingMember: false,
        showProgress: false, progressForm: { id: null, name: '', progress: 0, remark: '' },
      };
    },
    computed: {
      canWrite: function () { return App.isManager(); },
    },
    mounted: function () { this.init(); },
    methods: {
      init: async function () {
        try {
          const [d, e] = await Promise.all([API.departments.list(), API.employees.options()]);
          this.depts = d.items;
          this.employees = e.items;
        } catch (err) { App.toast(err.message, 'error'); }
        this.load();
        this.loadStats();
      },
      load: async function () {
        this.loading = true;
        try {
          const params = Object.assign({ page: this.page, size: this.size }, this.query);
          const res = await API.projects.list(params);
          this.rows = res.items;
          this.total = res.total;
          this.pages = res.pages;
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.loading = false; }
      },
      loadStats: async function () {
        try { this.stats = await API.projects.stats(); } catch (e) { /* 忽略 */ }
      },
      search: function () { this.page = 1; this.load(); },
      reset: function () {
        this.query = { keyword: '', status: '', priority: '', department_id: null, mine: false };
        this.page = 1;
        this.load();
      },
      changePage: function (p) { this.page = p; this.load(); },
      changeSize: function (s) { this.size = s; this.page = 1; this.load(); },

      /* ------------------------------------------------ 新增 / 编辑 */
      openCreate: function () {
        this.form = EMPTY_FORM();
        this.showForm = true;
      },
      openEdit: function (row) {
        const f = EMPTY_FORM();
        Object.keys(f).forEach(function (k) {
          if (row[k] !== undefined && row[k] !== null) f[k] = row[k];
        });
        f.budget = row.budget === null || row.budget === undefined ? '' : row.budget;
        this.form = f;
        this.showForm = true;
      },
      save: async function () {
        if (!this.form.name) { App.toast('请填写项目名称', 'error'); return; }
        if (!this.form.department_id) { App.toast('请选择归属部门', 'error'); return; }
        this.saving = true;
        try {
          const payload = Object.assign({}, this.form);
          delete payload.id;
          if (payload.budget === '') payload.budget = null;
          ['start_date', 'end_date'].forEach(function (k) { if (!payload[k]) payload[k] = null; });
          if (this.form.id) {
            await API.projects.update(this.form.id, payload);
            App.toast('项目已更新', 'success');
          } else {
            await API.projects.create(payload);
            App.toast('项目已创建', 'success');
          }
          this.showForm = false;
          this.load();
          this.loadStats();
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.saving = false; }
      },
      remove: async function (row) {
        const ok = await App.confirm({
          title: '删除项目',
          message: '确定要删除项目「' + row.name + '」吗？',
          detail: row.report_count > 0
            ? '该项目下还有 ' + row.report_count + ' 份报告，需要先删除报告才能删除项目。'
            : '删除后项目及其成员关系将一并清除，无法恢复。',
          danger: true, okText: '确认删除',
        });
        if (!ok) return;
        try {
          const res = await API.projects.remove(row.id);
          App.toast(res.message, 'success');
          this.load();
          this.loadStats();
        } catch (e) { App.toast(e.message, 'error'); }
      },

      /* ------------------------------------------------ 详情与成员 */
      openDetail: async function (row) {
        try {
          this.detail = await API.projects.get(row.id);
          this.showDetail = true;
        } catch (e) { App.toast(e.message, 'error'); }
      },
      openMember: function () {
        this.memberPick = [];
        this.memberRole = '开发';
        this.showMember = true;
      },
      addMembers: async function () {
        if (!this.memberPick.length) { App.toast('请选择要添加的员工', 'warning'); return; }
        this.savingMember = true;
        try {
          const members = this.memberPick.map((id) => ({ employee_id: id, role: this.memberRole }));
          const res = await API.projects.addMembers(this.detail.id, members);
          App.toast(res.message, 'success');
          this.showMember = false;
          this.openDetail(this.detail);
          this.load();
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.savingMember = false; }
      },
      removeMember: async function (m) {
        const ok = await App.confirm({
          title: '移出项目', message: '确定要把「' + m.name + '」移出该项目吗？',
        });
        if (!ok) return;
        try {
          const res = await API.projects.removeMember(this.detail.id, m.id);
          App.toast(res.message, 'success');
          this.openDetail(this.detail);
          this.load();
        } catch (e) { App.toast(e.message, 'error'); }
      },

      /* ------------------------------------------------ 进度 */
      openProgress: function (row) {
        this.progressForm = { id: row.id, name: row.name, progress: row.progress, remark: '' };
        this.showProgress = true;
      },
      saveProgress: async function () {
        try {
          const res = await API.projects.updateProgress(
            this.progressForm.id, App.num(this.progressForm.progress), this.progressForm.remark);
          App.toast(res.message, 'success');
          this.showProgress = false;
          this.load();
          this.loadStats();
          if (this.showDetail && this.detail && this.detail.id === this.progressForm.id) {
            this.openDetail(this.detail);
          }
        } catch (e) { App.toast(e.message, 'error'); }
      },

      /* ------------------------------------------------ 小工具 */
      fmt: function (v) { return App.dateOnly(v); },
      money: function (v) { return v === null || v === undefined ? '—' : '¥' + App.money(v); },
      deadlineText: function (p) {
        if (p.status === '已完成' || p.status === '已归档') return '已结束';
        if (p.days_left === null || p.days_left === undefined) return '未设置截止日期';
        if (p.days_left < 0) return '已逾期 ' + Math.abs(p.days_left) + ' 天';
        if (p.days_left === 0) return '今天截止';
        return '剩余 ' + p.days_left + ' 天';
      },
      deadlineClass: function (p) {
        if (p.status === '已完成' || p.status === '已归档') return 'text-muted';
        if (p.days_left === null || p.days_left === undefined) return 'text-light';
        if (p.days_left < 0) return 'text-danger';
        if (p.days_left <= 7) return 'text-warning';
        return 'text-muted';
      },
      barClass: function (p) { return App.progressClass(p.progress, p.status); },
    },
    template: `
      <div>
        <!-- ============ 统计条 ============ -->
        <div class="grid c4 mb2" v-if="stats">
          <stat-card label="项目总数" :value="stats.total" :foot="'进行中 ' + stats.active + ' 个'"
                     accent="1" icon="📁"></stat-card>
          <stat-card label="平均进度" :value="stats.avg_progress + '%'" foot="仅统计进行中的项目"
                     accent="2" icon="📈"></stat-card>
          <stat-card label="逾期项目" :value="stats.overdue" foot="已超计划结束日期"
                     accent="5" icon="⏰"></stat-card>
          <stat-card label="项目报告" :value="stats.report_total" foot="关联到项目的报告总数"
                     accent="3" icon="📄"></stat-card>
        </div>

        <!-- ============ 筛选栏 ============ -->
        <div class="card">
          <div class="filters">
            <input class="grow" type="text" v-model="query.keyword" @keyup.enter="search"
                   placeholder="搜索项目名称 / 编号 / 客户 ...">
            <select v-model="query.status" @change="search">
              <option value="">全部状态</option>
              <option v-for="s in statusList" :key="s" :value="s">{{ s }}</option>
            </select>
            <select v-model="query.priority" @change="search">
              <option value="">全部优先级</option>
              <option v-for="p in priorityList" :key="p" :value="p">{{ p }}</option>
            </select>
            <dept-select v-model="query.department_id" :depts="depts" placeholder="全部部门"
                         @update:modelValue="search"></dept-select>
            <label class="fs13 flex-center gap1" style="cursor:pointer">
              <input type="checkbox" v-model="query.mine" @change="search" style="width:auto">
              只看我参与的
            </label>
            <button class="btn primary" @click="search">🔍 查询</button>
            <button class="btn" @click="reset">重置</button>

            <div class="spacer"></div>

            <button class="btn" @click="view = view === 'card' ? 'table' : 'card'">
              {{ view === 'card' ? '📋 列表视图' : '🗂️ 卡片视图' }}
            </button>
            <button class="btn primary" v-if="canWrite" @click="openCreate">➕ 新建项目</button>
          </div>

          <!-- ============ 内容区 ============ -->
          <div class="card-body">
            <loading v-if="loading"></loading>
            <empty-state v-else-if="!rows.length" icon="📁" text="没有符合条件的项目"
                         hint="试着调整筛选条件，或新建一个项目">
              <button class="btn primary" v-if="canWrite" @click="openCreate">➕ 新建项目</button>
            </empty-state>

            <!-- 卡片视图 -->
            <div class="grid c3" v-else-if="view === 'card'">
              <div class="card project-card" v-for="p in rows" :key="p.id" style="margin:0">
                <div class="pc-head">
                  <h4 class="link" @click="openDetail(p)">{{ p.name }}</h4>
                  <status-tag :status="p.priority" :text="'优先级 ' + p.priority"></status-tag>
                </div>
                <div class="flex-center gap1">
                  <status-tag :status="p.status"></status-tag>
                  <span class="tag outline mono">{{ p.code }}</span>
                </div>
                <div class="pc-meta">
                  <div>👤 负责人：{{ p.owner_name || '未指定' }} · 🏢 {{ p.department_name || '未分配' }}</div>
                  <div>🏷️ 客户：{{ p.customer || '内部项目' }}</div>
                  <div>📅 {{ fmt(p.start_date) }} ~ {{ fmt(p.end_date) }}</div>
                  <div :class="deadlineClass(p)">⏱️ {{ deadlineText(p) }}</div>
                  <div>💰 预算：{{ money(p.budget) }} · 👥 {{ p.member_count }} 人 · 📄 {{ p.report_count }} 份报告</div>
                </div>
                <div>
                  <div class="flex-between fs12 text-muted" style="margin-bottom:4px">
                    <span>进度</span><span>{{ p.progress }}%</span>
                  </div>
                  <div class="bar" :class="barClass(p)"><i :style="{ width: p.progress + '%' }"></i></div>
                </div>
                <div class="pc-foot">
                  <button class="btn xs" @click="openDetail(p)">详情</button>
                  <button class="btn xs" @click="openProgress(p)">更新进度</button>
                  <button class="btn xs" v-if="canWrite" @click="openEdit(p)">编辑</button>
                  <button class="btn xs danger" v-if="canWrite" @click="remove(p)">删除</button>
                </div>
              </div>
            </div>

            <!-- 列表视图 -->
            <div class="table-wrap" v-else>
              <table class="data">
                <thead>
                  <tr>
                    <th>项目编号</th><th>项目名称</th><th>客户</th><th>状态</th><th>优先级</th>
                    <th>负责人</th><th>部门</th><th style="min-width:150px">进度</th>
                    <th>截止日期</th><th class="num">报告</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="p in rows" :key="p.id">
                    <td class="mono">{{ p.code }}</td>
                    <td class="strong link" @click="openDetail(p)">{{ p.name }}</td>
                    <td>{{ p.customer || '—' }}</td>
                    <td><status-tag :status="p.status"></status-tag></td>
                    <td><status-tag :status="p.priority"></status-tag></td>
                    <td>{{ p.owner_name || '—' }}</td>
                    <td class="fs12">{{ p.department_name || '—' }}</td>
                    <td><progress-bar :value="p.progress" :status="p.status"></progress-bar></td>
                    <td>
                      <div class="fs12">{{ fmt(p.end_date) }}</div>
                      <div class="fs12" :class="deadlineClass(p)">{{ deadlineText(p) }}</div>
                    </td>
                    <td class="num">{{ p.report_count }}</td>
                    <td class="actions">
                      <button class="btn xs" @click="openDetail(p)">详情</button>
                      <button class="btn xs" @click="openProgress(p)">进度</button>
                      <button class="btn xs" v-if="canWrite" @click="openEdit(p)">编辑</button>
                      <button class="btn xs danger" v-if="canWrite" @click="remove(p)">删除</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <pagination v-if="!loading && rows.length" :page="page" :pages="pages" :total="total"
                      :size="size" @update:page="changePage" @update:size="changeSize"></pagination>
        </div>

        <!-- ============ 新建 / 编辑 ============ -->
        <modal v-if="showForm" :title="form.id ? '编辑项目' : '新建项目'"
               size="wide" :loading="saving" @close="showForm = false" @ok="save">
          <div class="form-grid c2">
            <div class="form-item">
              <label>项目名称 <span class="req">*</span></label>
              <input type="text" v-model="form.name" placeholder="如 企业级协同办公平台">
            </div>
            <div class="form-item">
              <label>项目编号</label>
              <input type="text" v-model="form.code" placeholder="留空自动生成，如 PRJ-2025-009">
            </div>
            <div class="form-item">
              <label>客户 / 甲方</label>
              <input type="text" v-model="form.customer" placeholder="如 中远集团，内部项目可留空">
            </div>
            <div class="form-item">
              <label>归属部门 <span class="req">*</span></label>
              <dept-select v-model="form.department_id" :depts="depts" placeholder="请选择部门"></dept-select>
            </div>
            <div class="form-item">
              <label>项目负责人</label>
              <select v-model="form.owner_id">
                <option :value="null">暂不指定</option>
                <option v-for="e in employees" :key="e.id" :value="e.id">
                  {{ e.name }}{{ e.position ? '（' + e.position + '）' : '' }}
                </option>
              </select>
            </div>
            <div class="form-item">
              <label>项目状态</label>
              <select v-model="form.status">
                <option v-for="s in statusList" :key="s" :value="s">{{ s }}</option>
              </select>
            </div>
            <div class="form-item">
              <label>优先级</label>
              <select v-model="form.priority">
                <option v-for="p in priorityList" :key="p" :value="p">{{ p }}</option>
              </select>
            </div>
            <div class="form-item">
              <label>预算（元）</label>
              <input type="number" v-model="form.budget" placeholder="可留空">
            </div>
            <div class="form-item">
              <label>开始日期</label>
              <input type="date" v-model="form.start_date">
            </div>
            <div class="form-item">
              <label>计划结束日期</label>
              <input type="date" v-model="form.end_date">
            </div>
            <div class="form-item full">
              <label>当前进度：{{ form.progress }}%</label>
              <input type="range" min="0" max="100" step="5" v-model.number="form.progress"
                     style="width:100%">
              <span class="hint">进度设为 100% 时，项目状态会自动变为「已完成」</span>
            </div>
            <div class="form-item full">
              <label>项目描述</label>
              <textarea v-model="form.description" placeholder="项目背景、目标、交付范围等"></textarea>
            </div>
          </div>
        </modal>

        <!-- ============ 详情 ============ -->
        <modal v-if="showDetail && detail" :title="'项目详情 — ' + detail.name"
               size="wide" :hideFooter="true" @close="showDetail = false">
          <div class="flex-center gap1 mb2 wrap">
            <status-tag :status="detail.status"></status-tag>
            <status-tag :status="detail.priority" :text="'优先级 ' + detail.priority"></status-tag>
            <span class="tag outline mono">{{ detail.code }}</span>
            <span class="tag" :class="deadlineClass(detail)">{{ deadlineText(detail) }}</span>
          </div>

          <div class="mb2">
            <div class="flex-between fs12 text-muted" style="margin-bottom:4px">
              <span>项目进度</span><span>{{ detail.progress }}%</span>
            </div>
            <div class="bar" :class="barClass(detail)" style="height:9px">
              <i :style="{ width: detail.progress + '%' }"></i>
            </div>
          </div>

          <div class="info-list mb2">
            <info-row label="客户" :value="detail.customer"></info-row>
            <info-row label="归属部门" :value="detail.department_name"></info-row>
            <info-row label="负责人" :value="detail.owner_name"></info-row>
            <info-row label="预算" :value="money(detail.budget)"></info-row>
            <info-row label="开始日期" :value="fmt(detail.start_date)"></info-row>
            <info-row label="结束日期" :value="fmt(detail.end_date)"></info-row>
            <info-row label="成员数量" :value="detail.member_count + ' 人'"></info-row>
            <info-row label="报告数量" :value="detail.report_count + ' 份'"></info-row>
            <info-row label="项目描述" :value="detail.description" full></info-row>
          </div>

          <div class="flex-between mb1">
            <div class="strong">项目成员（{{ detail.members.length }}）</div>
            <button class="btn sm" v-if="canWrite" @click="openMember">➕ 添加成员</button>
          </div>
          <div class="table-wrap mb2" v-if="detail.members.length">
            <table class="data">
              <thead><tr><th>姓名</th><th>工号</th><th>部门</th><th>项目内角色</th><th></th></tr></thead>
              <tbody>
                <tr v-for="m in detail.members" :key="m.id">
                  <td class="strong">{{ m.name }}</td>
                  <td class="mono">{{ m.emp_no }}</td>
                  <td class="fs12">{{ m.department_name || '—' }}</td>
                  <td><span class="tag blue">{{ m.role || '成员' }}</span></td>
                  <td class="actions">
                    <button class="btn xs danger" v-if="canWrite" @click="removeMember(m)">移出</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="fs13 text-light mb2" v-else>还没有添加项目成员</div>

          <div class="strong mb1">项目报告（{{ detail.reports.length }}）</div>
          <div class="table-wrap" v-if="detail.reports.length">
            <table class="data">
              <thead><tr><th>报告名称</th><th>分类</th><th>版本</th><th>上传人</th><th>日期</th></tr></thead>
              <tbody>
                <tr v-for="r in detail.reports" :key="r.id">
                  <td>{{ r.title }}</td>
                  <td><span class="tag blue">{{ r.category }}</span></td>
                  <td>v{{ r.version }}</td>
                  <td>{{ r.uploader_name || '—' }}</td>
                  <td class="fs12 text-muted">{{ fmt(r.report_date) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="fs13 text-light" v-else>
            还没有上传报告 —— 可以到「报告管理」页面上传，上传时选择本项目即可
          </div>
        </modal>

        <!-- ============ 添加成员 ============ -->
        <modal v-if="showMember" title="添加项目成员" :loading="savingMember"
               okText="添加" @close="showMember = false" @ok="addMembers">
          <div class="form-item mb2">
            <label>项目内角色</label>
            <select v-model="memberRole">
              <option>开发</option><option>测试</option><option>设计</option>
              <option>需求</option><option>实施</option><option>项目负责人</option>
            </select>
          </div>
          <div class="form-item">
            <label>选择员工（可多选，按住 Ctrl / Shift）</label>
            <select v-model="memberPick" multiple size="10" style="height:auto;padding:6px">
              <option v-for="e in employees" :key="e.id" :value="e.id">
                {{ e.name }} · {{ e.department_name || '未分配' }}{{ e.position ? ' · ' + e.position : '' }}
              </option>
            </select>
            <span class="hint">已选 {{ memberPick.length }} 人</span>
          </div>
        </modal>

        <!-- ============ 更新进度 ============ -->
        <modal v-if="showProgress" title="更新项目进度" :size="'narrow'"
               okText="保存进度" @close="showProgress = false" @ok="saveProgress">
          <div class="fs13 text-muted mb2">{{ progressForm.name }}</div>
          <div class="form-item mb2">
            <label>当前进度：<b>{{ progressForm.progress }}%</b></label>
            <input type="range" min="0" max="100" step="5" v-model.number="progressForm.progress"
                   style="width:100%">
          </div>
          <div class="form-item">
            <label>进度说明（写入操作日志）</label>
            <textarea v-model="progressForm.remark" placeholder="如：完成审批流联调，进入测试阶段"></textarea>
          </div>
        </modal>
      </div>`,
  };
})();
