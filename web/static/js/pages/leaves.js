/* ==========================================================================
   请假审批：提交申请、待办审批、部门视图、撤销
   ========================================================================== */
(function () {
  'use strict';

  window.PageLeaves = {
    inject: ['refreshBadges'],
    data: function () {
      return {
        tab: 'mine',
        loading: false,
        rows: [], total: 0, page: 1, size: 20, pages: 1,
        query: { status: '', leave_type: '', employee_id: null },
        types: [],
        employees: [],
        stats: null,
        statsMonth: '',

        // 提交申请
        showForm: false, saving: false,
        form: { leave_type: '事假', start_date: App.today(), end_date: App.today(),
                days: 1, reason: '' },

        // 审批
        showApprove: false, approving: false, current: null,
        approveForm: { action: 'approve', comment: '' },

        // 详情
        showDetail: false, detail: null,
      };
    },
    computed: {
      canApprove: function () { return App.isManager(); },
      isAdmin: function () { return App.isAdmin(); },
      daysText: function () {
        const s = this.form.start_date, e = this.form.end_date;
        if (!s || !e || e < s) return '请检查日期';
        const d = Math.round((new Date(e) - new Date(s)) / 86400000) + 1;
        return '共 ' + d + ' 天（含首尾，按自然日计算）';
      },
    },
    mounted: function () { this.init(); },
    methods: {
      init: async function () {
        try {
          const [t, e] = await Promise.all([API.leaves.types(), API.employees.options()]);
          this.types = t.items;
          this.employees = e.items;
        } catch (err) { /* 忽略 */ }
        this.load();
        this.loadStats();
      },
      load: async function () {
        this.loading = true;
        try {
          const params = Object.assign({ scope: this.tab, page: this.page, size: this.size }, this.query);
          const res = await API.leaves.list(params);
          this.rows = res.items;
          this.total = res.total;
          this.pages = res.pages;
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.loading = false; }
      },
      loadStats: async function () {
        try {
          this.stats = await API.leaves.stats(this.statsMonth ? { month: this.statsMonth } : {});
        } catch (e) { /* 忽略 */ }
      },
      switchTab: function (t) {
        // 普通员工没有审批和部门视图权限，界面上直接不给入口
        if ((t === 'pending' || t === 'dept') && !this.canApprove) {
          App.toast('普通员工只能查看自己的申请记录', 'warning');
          return;
        }
        this.tab = t;
        this.page = 1;
        this.query.status = '';
        this.load();
      },
      search: function () { this.page = 1; this.load(); },
      reset: function () {
        this.query = { status: '', leave_type: '', employee_id: null };
        this.search();
      },
      changePage: function (p) { this.page = p; this.load(); },
      changeSize: function (s) { this.size = s; this.page = 1; this.load(); },

      /* ------------------------------------------------ 提交申请 */
      openForm: function () {
        this.form = { leave_type: '事假', start_date: App.today(), end_date: App.today(),
                      days: 1, reason: '' };
        this.showForm = true;
      },
      submit: async function () {
        if (!this.form.start_date || !this.form.end_date) {
          App.toast('请选择开始和结束日期', 'error'); return;
        }
        if (this.form.end_date < this.form.start_date) {
          App.toast('结束日期不能早于开始日期', 'error'); return;
        }
        this.saving = true;
        try {
          const res = await API.leaves.create({
            leave_type: this.form.leave_type,
            start_date: this.form.start_date,
            end_date: this.form.end_date,
            reason: this.form.reason,
          });
          App.toast(res.message, 'success');
          this.showForm = false;
          this.tab = 'mine';
          this.load();
          this.loadStats();
          this.refreshBadges();
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.saving = false; }
      },

      /* ------------------------------------------------ 审批 */
      openApprove: function (row) {
        this.current = row;
        this.approveForm = { action: 'approve', comment: '' };
        this.showApprove = true;
      },
      doApprove: async function () {
        if (this.approveForm.action === 'reject' && !this.approveForm.comment.trim()) {
          App.toast('驳回时请填写审批意见', 'error'); return;
        }
        this.approving = true;
        try {
          const res = await API.leaves.approve(
            this.current.id, this.approveForm.action, this.approveForm.comment);
          App.toast(res.message, 'success');
          this.showApprove = false;
          this.load();
          this.loadStats();
          this.refreshBadges();
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.approving = false; }
      },

      /* ------------------------------------------------ 撤销 / 删除 */
      cancel: async function (row) {
        const ok = await App.confirm({
          title: '撤销申请',
          message: '确定要撤销这条' + row.leave_type + '申请吗？',
          detail: row.start_date + ' ~ ' + row.end_date + '（' + row.days + ' 天）',
        });
        if (!ok) return;
        try {
          const res = await API.leaves.cancel(row.id);
          App.toast(res.message, 'success');
          this.load();
          this.loadStats();
          this.refreshBadges();
        } catch (e) { App.toast(e.message, 'error'); }
      },
      remove: async function (row) {
        const ok = await App.confirm({
          title: '删除记录', message: '确定要删除这条请假记录吗？', danger: true, okText: '删除',
        });
        if (!ok) return;
        try {
          const res = await API.leaves.remove(row.id);
          App.toast(res.message, 'success');
          this.load();
        } catch (e) { App.toast(e.message, 'error'); }
      },
      openDetail: async function (row) {
        try {
          this.detail = await API.leaves.get(row.id);
          this.showDetail = true;
        } catch (e) { App.toast(e.message, 'error'); }
      },

      fmt: function (v) { return App.dateOnly(v); },
    },
    template: `
      <div>
        <!-- ================= 统计 ================= -->
        <div class="grid c4 mb2" v-if="stats">
          <stat-card label="申请总数" :value="stats.total" :foot="statsMonth ? statsMonth : '全部时间'"
                     accent="1" icon="📝"></stat-card>
          <stat-card label="待审批" :value="stats.by_status['待审批'] || 0" foot="需要主管处理"
                     accent="3" icon="⏳"></stat-card>
          <stat-card label="已通过" :value="stats.by_status['已通过'] || 0"
                     :foot="'合计请假 ' + stats.total_days + ' 天'" accent="2" icon="✅"></stat-card>
          <stat-card label="已驳回" :value="stats.by_status['已驳回'] || 0" foot="未获批准的申请"
                     accent="5" icon="🚫"></stat-card>
        </div>

        <div class="card">
          <div class="tabs">
            <div class="tab" :class="{ active: tab === 'mine' }" @click="switchTab('mine')">
              我的申请
            </div>
            <div class="tab" v-if="canApprove" :class="{ active: tab === 'pending' }"
                 @click="switchTab('pending')">
              待我审批
            </div>
            <div class="tab" v-if="canApprove" :class="{ active: tab === 'dept' }"
                 @click="switchTab('dept')">
              部门记录
            </div>
          </div>

          <div class="filters">
            <select v-model="query.status" @change="search">
              <option value="">全部状态</option>
              <option value="待审批">待审批</option>
              <option value="已通过">已通过</option>
              <option value="已驳回">已驳回</option>
              <option value="已撤销">已撤销</option>
            </select>
            <select v-model="query.leave_type" @change="search">
              <option value="">全部类型</option>
              <option v-for="t in types" :key="t" :value="t">{{ t }}</option>
            </select>
            <input type="month" v-model="statsMonth" title="按月份筛选统计"
                   @change="loadStats">
            <button class="btn primary" @click="search">🔍 查询</button>
            <button class="btn" @click="reset">重置</button>
            <div class="spacer"></div>
            <button class="btn primary" @click="openForm">➕ 提交请假申请</button>
          </div>

          <div class="card-body tight">
            <loading v-if="loading"></loading>
            <empty-state v-else-if="!rows.length" icon="📝" text="暂无请假申请记录"
                         :hint="tab === 'pending' ? '很好，当前没有待审批的申请' : '点击右上角提交一条申请试试'">
              <button class="btn primary" v-if="tab === 'mine'" @click="openForm">➕ 提交申请</button>
            </empty-state>
            <div class="table-wrap" v-else>
              <table class="data">
                <thead>
                  <tr>
                    <th>申请人</th><th>部门</th><th>类型</th><th>请假区间</th>
                    <th class="num">天数</th><th>事由</th><th>状态</th>
                    <th>审批人</th><th>审批意见</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in rows" :key="r.id">
                    <td>
                      <span class="strong link" @click="openDetail(r)">{{ r.employee_name }}</span>
                      <span class="tag red" style="margin-left:5px" v-if="r.is_mine">我</span>
                    </td>
                    <td class="fs12">{{ r.department_name || '—' }}</td>
                    <td><span class="tag purple">{{ r.leave_type }}</span></td>
                    <td class="fs12 nowrap">{{ r.start_date }} ~ {{ r.end_date }}</td>
                    <td class="num">{{ r.days }}</td>
                    <td class="fs12" style="max-width:220px">{{ r.reason || '—' }}</td>
                    <td><status-tag :status="r.status"></status-tag></td>
                    <td class="fs12">{{ r.approver_name || '—' }}</td>
                    <td class="fs12 text-muted" style="max-width:160px">{{ r.approve_comment || '—' }}</td>
                    <td class="actions">
                      <button class="btn xs primary" v-if="r.can_approve" @click="openApprove(r)">
                        审批
                      </button>
                      <button class="btn xs" v-if="r.is_mine && r.status === '待审批'"
                              @click="cancel(r)">撤销</button>
                      <button class="btn xs danger"
                              v-if="isAdmin || (r.is_mine && (r.status === '已驳回' || r.status === '已撤销'))"
                              @click="remove(r)">删除</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <pagination v-if="!loading && rows.length" :page="page" :pages="pages" :total="total"
                      :size="size" @update:page="changePage" @update:size="changeSize"></pagination>
        </div>

        <!-- ================= 提交申请 ================= -->
        <modal v-if="showForm" title="提交请假申请" :loading="saving"
               okText="提交申请" @close="showForm = false" @ok="submit">
          <div class="form-grid c2">
            <div class="form-item">
              <label>请假类型 <span class="req">*</span></label>
              <select v-model="form.leave_type">
                <option v-for="t in types" :key="t" :value="t">{{ t }}</option>
              </select>
            </div>
            <div class="form-item">
              <label>开始日期 <span class="req">*</span></label>
              <input type="date" v-model="form.start_date">
            </div>
            <div class="form-item">
              <label>结束日期 <span class="req">*</span></label>
              <input type="date" v-model="form.end_date">
            </div>
            <div class="form-item">
              <label>预计天数</label>
              <input type="text" :value="daysText" disabled>
            </div>
            <div class="form-item full">
              <label>请假事由</label>
              <textarea v-model="form.reason" placeholder="请说明请假原因，便于主管审批"></textarea>
            </div>
          </div>
          <div class="fs12 text-muted mt2">
            提交后由部门主管或系统管理员审批；审批通过后，请假期间会自动在考勤记录中标记为「请假」。
          </div>
        </modal>

        <!-- ================= 审批 ================= -->
        <modal v-if="showApprove && current" title="审批请假申请" :loading="approving"
               okText="提交审批结果" @close="showApprove = false" @ok="doApprove">
          <div class="info-list mb2">
            <info-row label="申请人" :value="current.employee_name"></info-row>
            <info-row label="部门" :value="current.department_name"></info-row>
            <info-row label="类型" :value="current.leave_type"></info-row>
            <info-row label="天数" :value="current.days + ' 天'"></info-row>
            <info-row label="开始" :value="current.start_date"></info-row>
            <info-row label="结束" :value="current.end_date"></info-row>
            <info-row label="事由" :value="current.reason" full></info-row>
          </div>
          <div class="form-item mb2">
            <label>审批结果</label>
            <div class="btn-group">
              <button class="btn" :class="approveForm.action === 'approve' ? 'success' : ''"
                      @click="approveForm.action = 'approve'">✅ 通过</button>
              <button class="btn" :class="approveForm.action === 'reject' ? 'danger' : ''"
                      @click="approveForm.action = 'reject'">🚫 驳回</button>
            </div>
          </div>
          <div class="form-item">
            <label>审批意见 {{ approveForm.action === 'reject' ? '（驳回必填）' : '' }}</label>
            <textarea v-model="approveForm.comment"
                      :placeholder="approveForm.action === 'reject'
                        ? '请说明驳回原因，如：当前项目处于关键期，建议改期'
                        : '可选，如：同意，注意交接工作'"></textarea>
          </div>
        </modal>

        <!-- ================= 详情 ================= -->
        <modal v-if="showDetail && detail" title="请假申请详情" :hideFooter="true"
               @close="showDetail = false">
          <div class="flex-center gap1 mb2">
            <status-tag :status="detail.status"></status-tag>
            <span class="tag purple">{{ detail.leave_type }}</span>
            <span class="fw">{{ detail.days }} 天</span>
          </div>
          <div class="info-list">
            <info-row label="申请人" :value="detail.employee_name"></info-row>
            <info-row label="工号" :value="detail.emp_no"></info-row>
            <info-row label="部门" :value="detail.department_name"></info-row>
            <info-row label="提交时间" :value="App.dateTime(detail.created_at)"></info-row>
            <info-row label="开始日期" :value="detail.start_date"></info-row>
            <info-row label="结束日期" :value="detail.end_date"></info-row>
            <info-row label="审批人" :value="detail.approver_name"></info-row>
            <info-row label="审批时间" :value="App.dateTime(detail.approved_at)"></info-row>
            <info-row label="请假事由" :value="detail.reason" full></info-row>
            <info-row label="审批意见" :value="detail.approve_comment" full></info-row>
          </div>
        </modal>
      </div>`,
  };
})();
