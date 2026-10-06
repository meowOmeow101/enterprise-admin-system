/* ==========================================================================
   数据看板：打卡入口 + KPI + 图表 + 待办
   ========================================================================== */
(function () {
  'use strict';

  window.PageDashboard = {
    inject: ['refreshBadges'],
    data: function () {
      return {
        loading: true,
        data: null,
        att: null,          // 今日考勤状态
        now: '',
        busy: false,
        clockTimer: null,
      };
    },
    computed: {
      emp: function () { return (this.data && this.data.employee) || {}; },
      proj: function () { return (this.data && this.data.project) || {}; },
      rep: function () { return (this.data && this.data.report) || {}; },
      atts: function () { return (this.data && this.data.attendance) || {}; },
      scopeText: function () {
        if (!this.data) return '';
        const s = this.data.scope;
        if (s.role === 'admin' || s.role === 'boss') return '全公司数据';
        if (s.role === 'manager') return (s.department || '本部门') + '及下级部门数据';
        return '你的个人数据';
      },
      canCheck: function () {
        return App.isManager() || (this.att && this.att.has_employee);
      },
      workHourText: function () {
        const r = this.att && this.att.record;
        return r && r.work_hours ? r.work_hours + ' 小时' : '—';
      },
    },
    mounted: function () {
      this.tick();
      this.clockTimer = setInterval(this.tick, 1000);
      this.load();
    },
    unmounted: function () { clearInterval(this.clockTimer); },
    methods: {
      tick: function () {
        const d = new Date();
        const week = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()];
        this.now = d.getFullYear() + '-' + App.pad(d.getMonth() + 1) + '-' + App.pad(d.getDate()) +
          ' 星期' + week + ' ' + App.pad(d.getHours()) + ':' + App.pad(d.getMinutes()) + ':' + App.pad(d.getSeconds());
      },
      load: async function () {
        this.loading = true;
        try {
          const tasks = [API.dashboard.overview()];
          tasks.push(API.attendance.today().catch(function () { return null; }));
          const res = await Promise.all(tasks);
          this.data = res[0];
          this.att = res[1];
        } catch (e) {
          App.toast(e.message, 'error');
        } finally {
          this.loading = false;
        }
      },
      checkIn: async function () {
        this.busy = true;
        try {
          const r = await API.attendance.checkIn();
          App.toast(r.message, 'success');
          await this.load();
          this.refreshBadges();
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.busy = false; }
      },
      checkOut: async function () {
        this.busy = true;
        try {
          const r = await API.attendance.checkOut();
          App.toast(r.message, 'success');
          await this.load();
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.busy = false; }
      },
      downloadReport: async function (r) {
        try {
          await API.reports.download(r.id, r.file_name);
          App.toast('已开始下载：' + r.file_name, 'success');
        } catch (e) { App.toast(e.message, 'error'); }
      },
      go: function (path) { this.$router.push(path); },
      money: function (v) { return App.money(v); },
      fmtDate: function (v) { return App.dateOnly(v); },
      fmtTime: function (v) { return App.dateTime(v); },
      fromNow: function (v) { return App.fromNow(v); },
      fileSize: function (v) { return App.fileSize(v); },
    },
    template: `
      <div>
        <loading v-if="loading"></loading>

        <template v-else-if="data">
          <!-- ============ 打卡 + 我的待办 ============ -->
          <div class="grid c2 mb2" style="grid-template-columns: 1.35fr 1fr">
            <div class="card" style="margin:0">
              <div class="card-body">
                <div class="flex-between wrap gap2">
                  <div>
                    <div class="fs12 text-muted">今日考勤 · {{ now }}</div>
                    <div class="flex-center gap2 mt1">
                      <div>
                        <div class="fs12 text-muted">上班</div>
                        <div class="strong" style="font-size:19px">
                          {{ att && att.record && att.record.check_in ? att.record.check_in : '--:--:--' }}
                        </div>
                      </div>
                      <div class="text-light">→</div>
                      <div>
                        <div class="fs12 text-muted">下班</div>
                        <div class="strong" style="font-size:19px">
                          {{ att && att.record && att.record.check_out ? att.record.check_out : '--:--:--' }}
                        </div>
                      </div>
                      <div>
                        <div class="fs12 text-muted">工时</div>
                        <div class="strong" style="font-size:19px">{{ workHourText }}</div>
                      </div>
                      <status-tag v-if="att && att.record" :status="att.record.status"></status-tag>
                    </div>
                  </div>
                  <div class="btn-group" v-if="canCheck">
                    <button class="btn primary" :disabled="busy || !att || !att.can_check_in" @click="checkIn">
                      🕘 上班打卡
                    </button>
                    <button class="btn success" :disabled="busy || !att || !att.can_check_out" @click="checkOut">
                      🏁 下班签退
                    </button>
                  </div>
                  <div v-else class="fs12 text-muted" style="max-width:220px">
                    当前账号未绑定员工档案，无法打卡。请联系管理员在「员工管理」中绑定账号。
                  </div>
                </div>
              </div>
            </div>

            <div class="card" style="margin:0">
              <div class="card-body">
                <div class="fs12 text-muted mb1">待我处理</div>
                <div class="grid c2" style="gap:10px">
                  <div @click="go('/leaves')" style="cursor:pointer">
                    <div class="kpi-value" style="font-size:22px;color:#b7791f">{{ data.leave.pending_total }}</div>
                    <div class="fs12 text-muted">待审批请假</div>
                  </div>
                  <div @click="go('/reports')" style="cursor:pointer">
                    <div class="kpi-value" style="font-size:22px;color:#2b6cb0">{{ rep.total }}</div>
                    <div class="fs12 text-muted">可见报告数</div>
                  </div>
                  <div @click="go('/announcements')" style="cursor:pointer">
                    <div class="kpi-value" style="font-size:22px;color:#805ad5">
                      {{ (data.announcements || []).filter(function(a){return !a.is_read}).length }}
                    </div>
                    <div class="fs12 text-muted">未读公告</div>
                  </div>
                  <div @click="go('/projects')" style="cursor:pointer">
                    <div class="kpi-value" style="font-size:22px;color:#2f855a">{{ proj.active }}</div>
                    <div class="fs12 text-muted">进行中项目</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- ============ KPI ============ -->
          <div class="grid c6 mb2">
            <stat-card label="在职员工" :value="emp.active" :foot="'共 ' + emp.total + ' 人（含离职）'"
                       accent="1" icon="👥"></stat-card>
            <stat-card label="试用期" :value="emp.probation" foot="处于试用期的员工"
                       accent="4" icon="🌱"></stat-card>
            <stat-card label="进行中项目" :value="proj.active" :foot="'平均进度 ' + proj.avg_progress + '%'"
                       accent="2" icon="📁"></stat-card>
            <stat-card label="逾期项目" :value="proj.overdue" foot="已过计划结束日期"
                       accent="5" icon="⏰"></stat-card>
            <stat-card label="项目报告" :value="rep.total" :foot="'累计下载 ' + rep.downloads + ' 次'"
                       accent="3" icon="📄"></stat-card>
            <stat-card label="今日已打卡" :value="atts.checked_in"
                       :foot="'迟到 ' + atts.late + ' · 未打卡 ' + atts.not_checked"
                       accent="1" icon="🕘"></stat-card>
          </div>

          <!-- ============ 图表区 ============ -->
          <div class="grid c3 mb2">
            <div class="card" style="margin:0">
              <div class="card-head"><h3>项目状态分布</h3><span class="sub">{{ scopeText }}</span></div>
              <div class="card-body"><pie-chart :data="proj.by_status" height="240px"></pie-chart></div>
            </div>
            <div class="card" style="margin:0">
              <div class="card-head"><h3>各部门人数</h3><span class="sub">不含离职</span></div>
              <div class="card-body"><h-bar-chart :data="emp.by_department" height="240px"></h-bar-chart></div>
            </div>
            <div class="card" style="margin:0">
              <div class="card-head"><h3>报告分类构成</h3><span class="sub">共 {{ rep.total }} 份</span></div>
              <div class="card-body"><pie-chart :data="rep.by_category" height="240px"></pie-chart></div>
            </div>
          </div>

          <div class="grid c2 mb2">
            <div class="card" style="margin:0">
              <div class="card-head"><h3>近 6 个月报告产出</h3></div>
              <div class="card-body"><bar-chart :data="rep.by_month" height="220px"></bar-chart></div>
            </div>
            <div class="card" style="margin:0">
              <div class="card-head"><h3>近 6 个月入职人数</h3></div>
              <div class="card-body"><line-chart :data="emp.hire_trend" height="220px"></line-chart></div>
            </div>
          </div>

          <!-- ============ 项目与报告 ============ -->
          <div class="grid c2 mb2">
            <div class="card" style="margin:0">
              <div class="card-head">
                <h3>重点项目进度</h3>
                <button class="btn sm ghost" @click="go('/projects')">全部项目 →</button>
              </div>
              <div class="card-body">
                <empty-state v-if="!proj.focus || !proj.focus.length" icon="📁" text="暂无进行中的项目"></empty-state>
                <div v-for="p in proj.focus" :key="p.id" style="margin-bottom:14px">
                  <div class="flex-between gap1" style="margin-bottom:5px">
                    <span class="link" @click="go('/projects')">{{ p.name }}</span>
                    <span class="fs12 text-muted nowrap">
                      {{ p.owner_name || '未指定负责人' }} · 截止 {{ fmtDate(p.end_date) }}
                    </span>
                  </div>
                  <progress-bar :value="p.progress" :status="p.status"></progress-bar>
                </div>
              </div>
            </div>

            <div class="card" style="margin:0">
              <div class="card-head">
                <h3>最新上传报告</h3>
                <button class="btn sm ghost" @click="go('/reports')">全部报告 →</button>
              </div>
              <div class="card-body tight">
                <empty-state v-if="!rep.recent || !rep.recent.length" icon="📄" text="暂无报告"></empty-state>
                <table class="data" v-else>
                  <thead><tr><th>报告名称</th><th>分类</th><th>上传人</th><th>时间</th><th></th></tr></thead>
                  <tbody>
                    <tr v-for="r in rep.recent" :key="r.id">
                      <td>
                        <div class="strong">{{ r.title }}</div>
                        <div class="fs12 text-light">{{ r.project_name || '未关联项目' }} ·
                          {{ fileSize(r.file_size) }}</div>
                      </td>
                      <td><span class="tag blue">{{ r.category }}</span></td>
                      <td>{{ r.uploader_name || '—' }}</td>
                      <td class="fs12 text-muted">{{ fromNow(r.created_at) }}</td>
                      <td class="actions">
                        <button class="btn xs" @click="downloadReport(r)">下载</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- ============ 公告 / 我的项目 / 动态 ============ -->
          <div class="grid c3">
            <div class="card" style="margin:0">
              <div class="card-head">
                <h3>公司公告</h3>
                <button class="btn sm ghost" @click="go('/announcements')">更多 →</button>
              </div>
              <div class="card-body">
                <empty-state v-if="!data.announcements.length" icon="📢" text="暂无公告"></empty-state>
                <div v-for="a in data.announcements" :key="a.id" class="mb2" style="cursor:pointer"
                     @click="go('/announcements')">
                  <div class="flex-center gap1">
                    <span class="tag red" v-if="a.is_pinned">置顶</span>
                    <span class="strong">{{ a.title }}</span>
                  </div>
                  <div class="fs12 text-light mt1">
                    {{ a.publisher_name || '系统' }} · {{ App.dateOnly(a.created_at) }}
                    <span class="tag blue" style="margin-left:6px" v-if="!a.is_read">未读</span>
                  </div>
                </div>
              </div>
            </div>

            <div class="card" style="margin:0">
              <div class="card-head"><h3>我参与的项目</h3></div>
              <div class="card-body">
                <empty-state v-if="!data.my_projects.length" icon="🙋"
                             text="你还没有参与任何项目"
                             hint="项目成员由部门主管在项目管理中维护"></empty-state>
                <div v-for="p in data.my_projects" :key="p.id" class="mb2">
                  <div class="flex-between gap1">
                    <span class="strong">{{ p.name }}</span>
                    <status-tag :status="p.status"></status-tag>
                  </div>
                  <div class="mt1"><progress-bar :value="p.progress" :status="p.status"></progress-bar></div>
                </div>
              </div>
            </div>

            <div class="card" style="margin:0">
              <div class="card-head"><h3>最近动态</h3></div>
              <div class="card-body">
                <empty-state v-if="!data.recent_logs.length" icon="🗂️" text="暂无操作记录"></empty-state>
                <ul class="timeline" v-else>
                  <li v-for="l in data.recent_logs" :key="l.id">
                    <div class="t-title">
                      <span class="tag" :class="App.statusClass(l.action)">{{ l.action }}</span>
                      {{ l.detail || l.module }}
                    </div>
                    <div class="t-time">{{ l.username || '系统' }} · {{ fromNow(l.created_at) }}</div>
                  </li>
                </ul>
              </div>
            </div>
          </div>

          <!-- ============ 逾期提醒 ============ -->
          <div class="card mt2" v-if="proj.overdue_list && proj.overdue_list.length">
            <div class="card-head"><h3>⚠️ 逾期项目提醒</h3><span class="sub">已超出计划结束日期</span></div>
            <div class="card-body tight">
              <table class="data">
                <thead><tr><th>项目名称</th><th>计划结束</th><th>当前进度</th><th></th></tr></thead>
                <tbody>
                  <tr v-for="p in proj.overdue_list" :key="p.id">
                    <td class="strong">{{ p.name }}</td>
                    <td class="text-danger">{{ fmtDate(p.end_date) }}</td>
                    <td style="width:200px"><progress-bar :value="p.progress"></progress-bar></td>
                    <td class="actions"><button class="btn xs" @click="go('/projects')">去处理</button></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>
      </div>`,
  };
})();
