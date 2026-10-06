/* ==========================================================================
   个人中心：资料维护、密码修改、我的考勤与操作记录
   ========================================================================== */
(function () {
  'use strict';

  window.PageProfile = {
    inject: ['setUser'],
    data: function () {
      return {
        tab: 'info',
        me: null,
        loading: true,
        saving: false,
        infoForm: { real_name: '', phone: '', email: '' },

        pwdForm: { old_password: '', new_password: '', confirm: '' },
        pwdSaving: false,

        // 我的考勤
        attMonth: App.thisMonth(),
        attRows: [], attLoading: false,

        // 我的操作记录
        logRows: [], logTotal: 0, logPage: 1, logPages: 1, logLoading: false,
      };
    },
    computed: {
      emp: function () { return (this.me && this.me.employee) || null; },
      attSummary: function () {
        const rows = this.attRows;
        return {
          days: rows.length,
          late: rows.filter(function (r) { return r.status === '迟到'; }).length,
          leave: rows.filter(function (r) { return r.status === '请假'; }).length,
          miss: rows.filter(function (r) { return r.status === '缺卡'; }).length,
          hours: rows.reduce(function (s, r) { return s + (r.work_hours || 0); }, 0).toFixed(1),
        };
      },
      pwdValid: function () {
        return this.pwdForm.old_password && this.pwdForm.new_password.length >= 6
          && this.pwdForm.new_password === this.pwdForm.confirm;
      },
    },
    mounted: function () { this.init(); },
    methods: {
      init: async function () {
        await this.loadMe();
        this.loadLogs();
      },
      loadMe: async function () {
        this.loading = true;
        try {
          this.me = await API.auth.me();
          this.infoForm = {
            real_name: this.me.real_name || '',
            phone: this.me.phone || '',
            email: this.me.email || '',
          };
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.loading = false; }
      },
      saveInfo: async function () {
        if (!this.infoForm.real_name.trim()) { App.toast('姓名不能为空', 'error'); return; }
        this.saving = true;
        try {
          const res = await API.auth.updateMe(this.infoForm);
          App.toast('个人资料已更新', 'success');
          this.me = Object.assign(this.me, res);
          this.setUser(res);            // 同步刷新顶部导航里的姓名
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.saving = false; }
      },
      changePassword: async function () {
        if (!this.pwdForm.old_password) { App.toast('请输入原密码', 'error'); return; }
        if (this.pwdForm.new_password.length < 6) { App.toast('新密码至少 6 位', 'error'); return; }
        if (this.pwdForm.new_password !== this.pwdForm.confirm) {
          App.toast('两次输入的新密码不一致', 'error'); return;
        }
        this.pwdSaving = true;
        try {
          await API.auth.changePassword({
            old_password: this.pwdForm.old_password,
            new_password: this.pwdForm.new_password,
          });
          App.toast('密码修改成功，请重新登录', 'success');
          this.pwdForm = { old_password: '', new_password: '', confirm: '' };
          const self = this;
          setTimeout(function () {
            API.store.clear();
            location.hash = '#/login';
            location.reload();
          }, 1200);
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.pwdSaving = false; }
      },

      switchTab: function (t) {
        this.tab = t;
        if (t === 'attendance' && !this.attRows.length) this.loadAttendance();
        if (t === 'logs') this.loadLogs();
      },
      loadAttendance: async function () {
        this.attLoading = true;
        try {
          const [y, m] = this.attMonth.split('-').map(Number);
          const res = await API.attendance.records({
            scope: 'mine', date_from: this.attMonth + '-01',
            date_to: this.attMonth + '-' + App.pad(new Date(y, m, 0).getDate()), size: 100,
          });
          this.attRows = res.items;
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.attLoading = false; }
      },
      loadLogs: async function () {
        this.logLoading = true;
        try {
          const res = await API.logs.mine({ page: this.logPage, size: 15 });
          this.logRows = res.items;
          this.logTotal = res.total;
          this.logPages = res.pages;
        } catch (e) { /* 忽略 */ }
        finally { this.logLoading = false; }
      },
      changeLogPage: function (p) { this.logPage = p; this.loadLogs(); },

      fmt: function (v) { return App.dateOnly(v); },
      roleLabel: function (v) { return App.roleLabel(v); },
      initials: function () { return App.initials(this.me && this.me.real_name); },
    },
    template: `
      <div>
        <loading v-if="loading"></loading>

        <template v-else-if="me">
          <!-- ================= 名片 ================= -->
          <div class="card">
            <div class="card-body">
              <div class="flex-center gap2 wrap">
                <div class="avatar lg" :style="{ background: App.avatarColor(me.real_name) }">
                  {{ initials() }}
                </div>
                <div style="flex:1;min-width:200px">
                  <div class="strong" style="font-size:18px">{{ me.real_name }}</div>
                  <div class="fs13 text-muted mt1">
                    {{ roleLabel(me.role) }} · {{ me.department_name || '未分配部门' }}
                    <span v-if="emp && emp.position"> · {{ emp.position }}</span>
                    <span v-if="emp && emp.job_level"> · {{ emp.job_level }}</span>
                  </div>
                  <div class="fs12 text-light mt1">
                    账号：{{ me.username }} · 工号：{{ emp ? emp.emp_no : '未绑定员工档案' }}
                    · 上次登录：{{ App.dateTime(me.last_login_at) }}
                  </div>
                </div>
                <div class="btn-group">
                  <span class="tag" :class="me.is_active ? 'green' : 'gray'">
                    {{ me.is_active ? '账号正常' : '账号已停用' }}
                  </span>
                  <span class="tag outline" v-if="emp">
                    <status-tag :status="emp.status"></status-tag>
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="tabs">
              <div class="tab" :class="{ active: tab === 'info' }" @click="switchTab('info')">
                基本资料
              </div>
              <div class="tab" :class="{ active: tab === 'password' }" @click="switchTab('password')">
                修改密码
              </div>
              <div class="tab" :class="{ active: tab === 'attendance' }" @click="switchTab('attendance')">
                我的考勤
              </div>
              <div class="tab" :class="{ active: tab === 'logs' }" @click="switchTab('logs')">
                我的操作记录
              </div>
            </div>

            <!-- ============ 基本资料 ============ -->
            <div class="card-body" v-if="tab === 'info'">
              <div class="grid c2">
                <div>
                  <div class="strong mb2">可编辑信息</div>
                  <div class="form-grid c1">
                    <div class="form-item">
                      <label>姓名 <span class="req">*</span></label>
                      <input type="text" v-model="infoForm.real_name">
                    </div>
                    <div class="form-item">
                      <label>手机号</label>
                      <input type="text" v-model="infoForm.phone" placeholder="11 位手机号">
                    </div>
                    <div class="form-item">
                      <label>邮箱</label>
                      <input type="text" v-model="infoForm.email">
                    </div>
                  </div>
                  <button class="btn primary mt2" :disabled="saving" @click="saveInfo">
                    {{ saving ? '保存中 ...' : '保存修改' }}
                  </button>
                </div>

                <div>
                  <div class="strong mb2">档案信息（只读）</div>
                  <div class="info-list">
                    <info-row label="工号" :value="emp ? emp.emp_no : ''"></info-row>
                    <info-row label="性别" :value="emp ? emp.gender : ''"></info-row>
                    <info-row label="部门" :value="me.department_name"></info-row>
                    <info-row label="职位" :value="emp ? emp.position : ''"></info-row>
                    <info-row label="职级" :value="emp ? emp.job_level : ''"></info-row>
                    <info-row label="员工状态" :value="emp ? emp.status : ''"></info-row>
                    <info-row label="入职日期" :value="emp ? fmt(emp.hire_date) : ''"></info-row>
                    <info-row label="学历" :value="emp ? emp.education : ''"></info-row>
                  </div>
                  <div class="fs12 text-light mt2">
                    如需修改工号、部门、职位等信息，请联系人事行政部或系统管理员在「员工管理」中调整。
                  </div>
                </div>
              </div>
            </div>

            <!-- ============ 修改密码 ============ -->
            <div class="card-body" v-if="tab === 'password'">
              <div style="max-width:420px">
                <div class="form-grid c1">
                  <div class="form-item">
                    <label>原密码 <span class="req">*</span></label>
                    <input type="password" v-model="pwdForm.old_password" autocomplete="current-password">
                  </div>
                  <div class="form-item">
                    <label>新密码 <span class="req">*</span></label>
                    <input type="password" v-model="pwdForm.new_password" autocomplete="new-password">
                    <span class="hint">至少 6 位，建议包含字母和数字</span>
                  </div>
                  <div class="form-item">
                    <label>确认新密码 <span class="req">*</span></label>
                    <input type="password" v-model="pwdForm.confirm" autocomplete="new-password">
                    <span class="hint text-danger"
                          v-if="pwdForm.confirm && pwdForm.new_password !== pwdForm.confirm">
                      两次输入不一致
                    </span>
                  </div>
                </div>
                <button class="btn primary mt2" :disabled="pwdSaving || !pwdValid"
                        @click="changePassword">
                  {{ pwdSaving ? '提交中 ...' : '确认修改密码' }}
                </button>
                <div class="fs12 text-muted mt2">
                  修改成功后需要重新登录；忘记密码请联系系统管理员在「账号管理」中重置。
                </div>
              </div>
            </div>

            <!-- ============ 我的考勤 ============ -->
            <div v-if="tab === 'attendance'">
              <div class="filters">
                <span class="fs13">月份</span>
                <input type="month" v-model="attMonth" @change="loadAttendance">
                <div class="spacer"></div>
                <span class="tag green">出勤 {{ attSummary.days }} 天</span>
                <span class="tag yellow">迟到 {{ attSummary.late }}</span>
                <span class="tag blue">请假 {{ attSummary.leave }}</span>
                <span class="tag red">缺卡 {{ attSummary.miss }}</span>
                <span class="tag outline">工时 {{ attSummary.hours }} h</span>
              </div>
              <div class="card-body tight">
                <loading v-if="attLoading"></loading>
                <empty-state v-else-if="!attRows.length" icon="🕘" text="该月份没有考勤记录"></empty-state>
                <div class="table-wrap" v-else>
                  <table class="data">
                    <thead>
                      <tr><th>日期</th><th>上班</th><th>下班</th><th class="num">工时</th>
                        <th>状态</th><th>备注</th></tr>
                    </thead>
                    <tbody>
                      <tr v-for="r in attRows" :key="r.id">
                        <td>{{ r.work_date }}</td>
                        <td>{{ r.check_in || '—' }}</td>
                        <td>{{ r.check_out || '—' }}</td>
                        <td class="num">{{ r.work_hours || '—' }}</td>
                        <td><status-tag :status="r.status"></status-tag></td>
                        <td class="fs12 text-muted">{{ r.remark || '' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <!-- ============ 我的操作记录 ============ -->
            <div v-if="tab === 'logs'">
              <div class="filters">
                <span class="fs13 text-muted">你在系统中的写操作都会留痕，方便自己核对</span>
                <div class="spacer"></div>
                <button class="btn sm" @click="loadLogs">🔄 刷新</button>
              </div>
              <div class="card-body tight">
                <loading v-if="logLoading"></loading>
                <empty-state v-else-if="!logRows.length" icon="🗂️" text="暂无操作记录"></empty-state>
                <div class="table-wrap" v-else>
                  <table class="data">
                    <thead>
                      <tr><th style="width:160px">时间</th><th style="width:90px">类型</th>
                        <th style="width:110px">模块</th><th>操作详情</th></tr>
                    </thead>
                    <tbody>
                      <tr v-for="r in logRows" :key="r.id">
                        <td class="fs12">{{ App.dateTime(r.created_at) }}</td>
                        <td><span class="tag" :class="App.statusClass(r.action)">{{ r.action }}</span></td>
                        <td class="fs12">{{ r.module }}</td>
                        <td class="fs13">{{ r.detail || '—' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
              <pagination v-if="!logLoading && logRows.length" :page="logPage" :pages="logPages"
                          :total="logTotal" :size="15" @update:page="changeLogPage"></pagination>
            </div>
          </div>
        </template>
      </div>`,
  };
})();
