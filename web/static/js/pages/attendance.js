/* ==========================================================================
   考勤：打卡、我的考勤视图、记录查询、月度汇总、补录
   ========================================================================== */
(function () {
  'use strict';

  window.PageAttendance = {
    data: function () {
      return {
        tab: 'mine',
        rules: null,
        today: null,
        now: '',
        clockTimer: null,
        busy: false,

        // 我的考勤
        myMonth: App.thisMonth(),
        myRows: [],
        myLoading: false,

        // 记录查询
        recLoading: false, recRows: [], recTotal: 0, recPage: 1, recSize: 31, recPages: 1,
        recQuery: { employee_id: null, department_id: null, date_from: '', date_to: '', status: '' },
        statusList: ['正常', '迟到', '早退', '缺卡', '旷工', '请假', '出差'],

        // 月度汇总
        sumMonth: App.thisMonth(), sumLoading: false, sumRows: [], sumWorkdays: 0,

        // 补录
        showEdit: false, saving: false,
        editForm: { employee_id: null, work_date: App.today(), check_in: '', check_out: '',
                    status: '', remark: '' },
        employees: [], depts: [],

        // 我的考勤日历
        calendar: [],
      };
    },
    computed: {
      canManage: function () { return App.isManager(); },
      myRecord: function () { return this.today && this.today.record; },
      mySummary: function () {
        const rows = this.myRows;
        return {
          total: rows.length,
          late: rows.filter(function (r) { return r.status === '迟到'; }).length,
          early: rows.filter(function (r) { return r.status === '早退'; }).length,
          leave: rows.filter(function (r) { return r.status === '请假'; }).length,
          miss: rows.filter(function (r) { return r.status === '缺卡'; }).length,
          hours: rows.reduce(function (s, r) { return s + (r.work_hours || 0); }, 0).toFixed(1),
        };
      },
    },
    mounted: function () {
      this.tick();
      this.clockTimer = setInterval(this.tick, 1000);
      this.init();
    },
    unmounted: function () { clearInterval(this.clockTimer); },
    methods: {
      tick: function () {
        const d = new Date();
        this.now = App.pad(d.getHours()) + ':' + App.pad(d.getMinutes()) + ':' + App.pad(d.getSeconds());
      },
      init: async function () {
        try {
          this.rules = await API.attendance.rules();
        } catch (e) { /* 忽略 */ }
        try {
          const res = await API.employees.options();
          this.employees = res.items;
        } catch (e) { /* 忽略 */ }
        try {
          const d = await API.departments.list();
          this.depts = d.items;
        } catch (e) { /* 忽略 */ }
        this.loadToday();
        this.loadMine();
      },
      loadToday: async function () {
        try { this.today = await API.attendance.today(); } catch (e) { /* 忽略 */ }
      },
      loadMine: async function () {
        this.myLoading = true;
        try {
          const first = this.myMonth + '-01';
          const [y, m] = this.myMonth.split('-').map(Number);
          const last = this.myMonth + '-' + App.pad(new Date(y, m, 0).getDate());
          const res = await API.attendance.records({
            scope: 'mine', date_from: first, date_to: last, size: 100,
          });
          this.myRows = res.items;
          this.buildCalendar(y, m);
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.myLoading = false; }
      },
      buildCalendar: function (year, month) {
        const byDate = {};
        this.myRows.forEach(function (r) { byDate[r.work_date] = r; });
        const days = new Date(year, month, 0).getDate();
        const list = [];
        const todayStr = App.today();
        for (let d = 1; d <= days; d++) {
          const dateStr = year + '-' + App.pad(month) + '-' + App.pad(d);
          const weekday = new Date(year, month - 1, d).getDay();
          const rec = byDate[dateStr];
          let cls = 'day-chip';
          if (weekday === 0 || weekday === 6) cls += ' weekend';
          else if (rec) {
            cls += { '正常': ' ok', '迟到': ' late', '早退': ' early',
                     '请假': ' leave', '缺卡': ' miss', '旷工': ' miss' }[rec.status] || '';
          }
          list.push({
            day: d, date: dateStr, weekday: weekday, record: rec, cls: cls,
            isToday: dateStr === todayStr, future: dateStr > todayStr,
          });
        }
        this.calendar = list;
      },
      changeMyMonth: function () { this.loadMine(); },

      checkIn: async function () {
        this.busy = true;
        try {
          const r = await API.attendance.checkIn();
          App.toast(r.message, r.record.status === '迟到' ? 'warning' : 'success');
          await this.loadToday();
          if (this.tab === 'mine') this.loadMine();
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.busy = false; }
      },
      checkOut: async function () {
        this.busy = true;
        try {
          const r = await API.attendance.checkOut();
          App.toast(r.message, 'success');
          await this.loadToday();
          if (this.tab === 'mine') this.loadMine();
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.busy = false; }
      },

      /* ------------------------------------------------ 记录查询 */
      loadRecords: async function () {
        this.recLoading = true;
        try {
          const params = Object.assign({ page: this.recPage, size: this.recSize }, this.recQuery);
          const res = await API.attendance.records(params);
          this.recRows = res.items;
          this.recTotal = res.total;
          this.recPages = res.pages;
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.recLoading = false; }
      },
      searchRecords: function () { this.recPage = 1; this.loadRecords(); },
      resetRecords: function () {
        this.recQuery = { employee_id: null, department_id: null, date_from: '', date_to: '', status: '' };
        this.searchRecords();
      },
      changeRecPage: function (p) { this.recPage = p; this.loadRecords(); },
      changeRecSize: function (s) { this.recSize = s; this.recPage = 1; this.loadRecords(); },

      /* ------------------------------------------------ 月度汇总 */
      loadSummary: async function () {
        this.sumLoading = true;
        try {
          const res = await API.attendance.summary({ month: this.sumMonth });
          this.sumRows = res.items;
          this.sumWorkdays = res.workdays;
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.sumLoading = false; }
      },

      /* ------------------------------------------------ 补录 */
      openCreate: function () {
        this.editForm = { employee_id: null, work_date: App.today(), check_in: '', check_out: '',
                          status: '', remark: '' };
        this.showEdit = true;
      },
      openEdit: function (row) {
        this.editForm = {
          employee_id: row.employee_id, work_date: row.work_date,
          check_in: row.check_in || '', check_out: row.check_out || '',
          status: row.status, remark: row.remark || '',
        };
        this.showEdit = true;
      },
      saveRecord: async function () {
        if (!this.editForm.employee_id) { App.toast('请选择员工', 'error'); return; }
        if (!this.editForm.work_date) { App.toast('请选择日期', 'error'); return; }
        this.saving = true;
        try {
          const payload = {
            employee_id: this.editForm.employee_id,
            work_date: this.editForm.work_date,
            check_in: this.editForm.check_in || null,
            check_out: this.editForm.check_out || null,
            status: this.editForm.status || null,
            remark: this.editForm.remark,
          };
          const res = await API.attendance.save(payload);
          App.toast(res.message, 'success');
          this.showEdit = false;
          this.loadRecords();
          if (this.tab === 'summary') this.loadSummary();
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.saving = false; }
      },
      removeRecord: async function (row) {
        const ok = await App.confirm({
          title: '删除考勤记录',
          message: '确定要删除 ' + row.employee_name + ' 在 ' + row.work_date + ' 的考勤记录吗？',
          danger: true, okText: '确认删除',
        });
        if (!ok) return;
        try {
          const res = await API.attendance.remove(row.id);
          App.toast(res.message, 'success');
          this.loadRecords();
        } catch (e) { App.toast(e.message, 'error'); }
      },

      switchTab: function (t) {
        this.tab = t;
        if (t === 'records' && !this.recRows.length) this.loadRecords();
        if (t === 'summary' && !this.sumRows.length) this.loadSummary();
      },
      fmt: function (v) { return App.dateOnly(v); },
    },
    template: `
      <div>
        <!-- ================= 打卡面板 ================= -->
        <div class="card">
          <div class="card-body">
            <div class="flex-between wrap gap2">
              <div>
                <div class="fs12 text-muted">当前时间</div>
                <div class="strong" style="font-size:30px;letter-spacing:1px">{{ now }}</div>
                <div class="fs12 text-muted mt1">
                  今天：{{ App.today() }} ·
                  工作时间 {{ rules ? rules.work_start + ' ~ ' + rules.work_end : '09:00 ~ 18:00' }} ·
                  晚于 {{ rules ? rules.late_after : '09:15' }} 打卡记为迟到
                </div>
              </div>

              <div class="flex-center gap2 wrap">
                <div class="text-center" style="min-width:96px">
                  <div class="fs12 text-muted">上班打卡</div>
                  <div class="strong" style="font-size:20px">
                    {{ myRecord && myRecord.check_in ? myRecord.check_in : '--:--:--' }}
                  </div>
                </div>
                <div class="text-center" style="min-width:96px">
                  <div class="fs12 text-muted">下班签退</div>
                  <div class="strong" style="font-size:20px">
                    {{ myRecord && myRecord.check_out ? myRecord.check_out : '--:--:--' }}
                  </div>
                </div>
                <div class="text-center" style="min-width:80px">
                  <div class="fs12 text-muted">今日工时</div>
                  <div class="strong" style="font-size:20px">
                    {{ myRecord && myRecord.work_hours ? myRecord.work_hours : '—' }}
                  </div>
                </div>
                <status-tag v-if="myRecord" :status="myRecord.status"></status-tag>
              </div>

              <div class="btn-group" v-if="today && today.has_employee">
                <button class="btn primary" :disabled="busy || !today.can_check_in" @click="checkIn">
                  🕘 上班打卡
                </button>
                <button class="btn success" :disabled="busy || !today.can_check_out" @click="checkOut">
                  🏁 下班签退
                </button>
              </div>
              <div v-else-if="today" class="fs12 text-muted" style="max-width:260px">
                当前账号未绑定员工档案，无法打卡。请联系管理员在「员工管理」中绑定账号。
              </div>
            </div>
          </div>
        </div>

        <!-- ================= 标签页 ================= -->
        <div class="card">
          <div class="tabs">
            <div class="tab" :class="{ active: tab === 'mine' }" @click="switchTab('mine')">我的考勤</div>
            <div class="tab" :class="{ active: tab === 'records' }" @click="switchTab('records')">
              考勤记录
            </div>
            <div class="tab" :class="{ active: tab === 'summary' }" @click="switchTab('summary')">
              月度汇总
            </div>
          </div>

          <!-- ============ 我的考勤 ============ -->
          <div v-if="tab === 'mine'">
            <div class="filters">
              <span class="fs13">统计月份</span>
              <input type="month" v-model="myMonth" @change="changeMyMonth">
              <div class="spacer"></div>
              <span class="tag green">出勤 {{ mySummary.total }} 天</span>
              <span class="tag yellow">迟到 {{ mySummary.late }}</span>
              <span class="tag yellow">早退 {{ mySummary.early }}</span>
              <span class="tag blue">请假 {{ mySummary.leave }}</span>
              <span class="tag red">缺卡 {{ mySummary.miss }}</span>
              <span class="tag outline">合计工时 {{ mySummary.hours }} h</span>
            </div>

            <div class="card-body">
              <loading v-if="myLoading"></loading>
              <template v-else>
                <div class="legend mb2">
                  <span><i class="dot" style="background:#9ae6b4"></i>正常</span>
                  <span><i class="dot" style="background:#f6e05e"></i>迟到 / 早退</span>
                  <span><i class="dot" style="background:#90cdf4"></i>请假</span>
                  <span><i class="dot" style="background:#feb2b2"></i>缺卡</span>
                  <span><i class="dot" style="background:#edf2f7"></i>周末 / 无记录</span>
                </div>
                <div class="calendar-strip">
                  <div v-for="d in calendar" :key="d.date" :class="d.cls"
                       :style="d.isToday ? 'outline:2px solid #2b6cb0' : ''"
                       :title="d.date + (d.record ? ' · ' + d.record.status +
                              (d.record.check_in ? ' 上班 ' + d.record.check_in : '') +
                              (d.record.check_out ? ' 下班 ' + d.record.check_out : '') : ' 无记录')">
                    <span class="d">{{ d.day }}</span>
                    <span>{{ d.record ? d.record.status : (d.future ? '' : '—') }}</span>
                  </div>
                </div>

                <div class="table-wrap mt3" v-if="myRows.length">
                  <table class="data">
                    <thead>
                      <tr><th>日期</th><th>上班</th><th>下班</th><th>工时</th>
                        <th>状态</th><th>备注</th></tr>
                    </thead>
                    <tbody>
                      <tr v-for="r in myRows" :key="r.id">
                        <td>{{ r.work_date }}</td>
                        <td>{{ r.check_in || '—' }}</td>
                        <td>{{ r.check_out || '—' }}</td>
                        <td>{{ r.work_hours || '—' }}</td>
                        <td><status-tag :status="r.status"></status-tag></td>
                        <td class="fs12 text-muted">{{ r.remark || '' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <empty-state v-else icon="🕘" text="本月还没有考勤记录"
                             hint="工作日记得先打上班卡，下班再签退"></empty-state>
              </template>
            </div>
          </div>

          <!-- ============ 考勤记录 ============ -->
          <div v-if="tab === 'records'">
            <div class="filters">
              <select v-model="recQuery.employee_id" @change="searchRecords">
                <option :value="null">全部员工</option>
                <option v-for="e in employees" :key="e.id" :value="e.id">{{ e.name }}</option>
              </select>
              <dept-select v-model="recQuery.department_id" :depts="depts" placeholder="全部部门"
                           @update:modelValue="searchRecords"></dept-select>
              <input type="date" v-model="recQuery.date_from" @change="searchRecords" title="起始日期">
              <span class="text-light">~</span>
              <input type="date" v-model="recQuery.date_to" @change="searchRecords" title="结束日期">
              <select v-model="recQuery.status" @change="searchRecords">
                <option value="">全部状态</option>
                <option v-for="s in statusList" :key="s" :value="s">{{ s }}</option>
              </select>
              <button class="btn primary" @click="searchRecords">🔍 查询</button>
              <button class="btn" @click="resetRecords">重置</button>
              <div class="spacer"></div>
              <button class="btn primary" v-if="canManage" @click="openCreate">➕ 补录考勤</button>
            </div>

            <div class="card-body tight">
              <loading v-if="recLoading"></loading>
              <empty-state v-else-if="!recRows.length" icon="🕘" text="没有符合条件的考勤记录"
                           hint="调整筛选条件，或使用补录功能添加记录"></empty-state>
              <div class="table-wrap" v-else>
                <table class="data">
                  <thead>
                    <tr><th>日期</th><th>姓名</th><th>工号</th><th>部门</th><th>上班</th>
                      <th>下班</th><th class="num">工时</th><th>状态</th><th>备注</th><th></th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="r in recRows" :key="r.id">
                      <td>{{ r.work_date }}</td>
                      <td class="strong">{{ r.employee_name }}</td>
                      <td class="mono fs12">{{ r.emp_no }}</td>
                      <td class="fs12">{{ r.department_name || '—' }}</td>
                      <td>{{ r.check_in || '—' }}</td>
                      <td>{{ r.check_out || '—' }}</td>
                      <td class="num">{{ r.work_hours || '—' }}</td>
                      <td><status-tag :status="r.status"></status-tag></td>
                      <td class="fs12 text-muted">{{ r.remark || '' }}</td>
                      <td class="actions" v-if="canManage">
                        <button class="btn xs" @click="openEdit(r)">修改</button>
                        <button class="btn xs danger" @click="removeRecord(r)">删除</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <pagination v-if="!recLoading && recRows.length" :page="recPage" :pages="recPages"
                        :total="recTotal" :size="recSize"
                        @update:page="changeRecPage" @update:size="changeRecSize"></pagination>
          </div>

          <!-- ============ 月度汇总 ============ -->
          <div v-if="tab === 'summary'">
            <div class="filters">
              <span class="fs13">统计月份</span>
              <input type="month" v-model="sumMonth" @change="loadSummary">
              <button class="btn" @click="loadSummary">🔄 重新统计</button>
              <div class="spacer"></div>
              <span class="fs12 text-muted">
                应出勤按当月周一至周五估算：<b>{{ sumWorkdays }}</b> 天
              </span>
            </div>
            <div class="card-body tight">
              <loading v-if="sumLoading"></loading>
              <empty-state v-else-if="!sumRows.length" icon="📊" text="暂无汇总数据"></empty-state>
              <div class="table-wrap" v-else>
                <table class="data">
                  <thead>
                    <tr><th>姓名</th><th>工号</th><th>部门</th>
                      <th class="num">应出勤</th><th class="num">实际打卡</th>
                      <th class="num">迟到</th><th class="num">早退</th>
                      <th class="num">请假</th><th class="num">缺卡</th>
                      <th class="num">合计工时</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="r in sumRows" :key="r.employee_id">
                      <td class="strong">{{ r.name }}</td>
                      <td class="mono fs12">{{ r.emp_no }}</td>
                      <td class="fs12">{{ r.department_name || '—' }}</td>
                      <td class="num">{{ r.workdays }}</td>
                      <td class="num">{{ r.attended }}</td>
                      <td class="num" :class="r.late ? 'text-warning strong' : ''">{{ r.late }}</td>
                      <td class="num" :class="r.early ? 'text-warning' : ''">{{ r.early }}</td>
                      <td class="num">{{ r.leave }}</td>
                      <td class="num" :class="r.missing ? 'text-danger strong' : ''">{{ r.missing }}</td>
                      <td class="num">{{ r.total_hours }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        <!-- ================= 补录弹窗 ================= -->
        <modal v-if="showEdit" title="考勤补录 / 修正" :loading="saving"
               okText="保存记录" @close="showEdit = false" @ok="saveRecord">
          <div class="form-grid c2">
            <div class="form-item">
              <label>员工 <span class="req">*</span></label>
              <select v-model="editForm.employee_id">
                <option :value="null">请选择员工</option>
                <option v-for="e in employees" :key="e.id" :value="e.id">
                  {{ e.name }}{{ e.department_name ? '（' + e.department_name + '）' : '' }}
                </option>
              </select>
            </div>
            <div class="form-item">
              <label>日期 <span class="req">*</span></label>
              <input type="date" v-model="editForm.work_date">
            </div>
            <div class="form-item">
              <label>上班时间</label>
              <input type="time" v-model="editForm.check_in">
              <span class="hint">留空表示没有打卡记录</span>
            </div>
            <div class="form-item">
              <label>下班时间</label>
              <input type="time" v-model="editForm.check_out">
            </div>
            <div class="form-item">
              <label>考勤状态</label>
              <select v-model="editForm.status">
                <option value="">自动判定</option>
                <option v-for="s in statusList" :key="s" :value="s">{{ s }}</option>
              </select>
              <span class="hint">留空则按打卡时间自动判定（迟到 / 早退 / 正常）</span>
            </div>
            <div class="form-item">
              <label>备注</label>
              <input type="text" v-model="editForm.remark" placeholder="如 忘记打卡，主管确认">
            </div>
          </div>
        </modal>
      </div>`,
  };
})();
