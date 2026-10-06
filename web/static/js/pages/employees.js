/* ==========================================================================
   员工管理：列表筛选、增删改查、批量操作、开通账号、Excel 导入导出
   ========================================================================== */
(function () {
  'use strict';

  const EMPTY_FORM = function () {
    return {
      id: null, emp_no: '', name: '', gender: '男', birth_date: '', phone: '', email: '',
      id_card: '', department_id: null, position: '', job_level: '', status: '在职',
      hire_date: App.today(), leave_date: '', salary: '', education: '本科', school: '',
      address: '', emergency_contact: '', emergency_phone: '', remark: '', user_id: null,
    };
  };

  window.PageEmployees = {
    data: function () {
      return {
        loading: true,
        rows: [], total: 0, page: 1, size: 20, pages: 1,
        depts: [], options: [],
        query: { keyword: '', department_id: null, status: '', gender: '', sort: 'id_desc' },
        selected: [],
        // 弹窗
        showForm: false, saving: false, form: EMPTY_FORM(),
        showDetail: false, detail: null,
        showImport: false, importing: false, importResult: null, importFile: null,
        showAccount: false, accountPwd: '123456', accountRole: 'employee', creatingAccounts: false,
        accountResult: null,
      };
    },
    computed: {
      canWrite: function () { return App.isManager(); },
      allChecked: function () {
        return this.rows.length > 0 && this.selected.length === this.rows.length;
      },
      statusList: function () { return ['在职', '试用期', '休假', '离职']; },
    },
    mounted: function () { this.init(); },
    methods: {
      init: async function () {
        try {
          const [deptRes, optRes] = await Promise.all([
            API.departments.list(), API.employees.options(),
          ]);
          this.depts = deptRes.items;
          this.options = optRes.items;
        } catch (e) { App.toast(e.message, 'error'); }
        this.load();
      },
      load: async function () {
        this.loading = true;
        try {
          const params = Object.assign({ page: this.page, size: this.size }, this.query);
          const res = await API.employees.list(params);
          this.rows = res.items;
          this.total = res.total;
          this.pages = res.pages;
          this.selected = [];
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.loading = false; }
      },
      search: function () { this.page = 1; this.load(); },
      reset: function () {
        this.query = { keyword: '', department_id: null, status: '', gender: '', sort: 'id_desc' };
        this.page = 1;
        this.load();
      },
      changePage: function (p) { this.page = p; this.load(); },
      changeSize: function (s) { this.size = s; this.page = 1; this.load(); },

      /* ------------------------------------------------ 选择 */
      toggleAll: function (e) {
        this.selected = e.target.checked ? this.rows.map(function (r) { return r.id; }) : [];
      },
      toggleOne: function (id) {
        const i = this.selected.indexOf(id);
        if (i >= 0) this.selected.splice(i, 1); else this.selected.push(id);
      },

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
        f.salary = row.salary === null || row.salary === undefined ? '' : row.salary;
        this.form = f;
        this.showForm = true;
      },
      save: async function () {
        if (!this.form.name) { App.toast('请填写姓名', 'error'); return; }
        this.saving = true;
        try {
          const payload = Object.assign({}, this.form);
          delete payload.id;
          if (payload.salary === '') payload.salary = null;
          ['birth_date', 'hire_date', 'leave_date'].forEach(function (k) {
            if (!payload[k]) payload[k] = null;
          });
          if (this.form.id) {
            await API.employees.update(this.form.id, payload);
            App.toast('员工信息已更新', 'success');
          } else {
            await API.employees.create(payload);
            App.toast('员工已添加', 'success');
          }
          this.showForm = false;
          this.load();
          this.refreshOptions();
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.saving = false; }
      },
      refreshOptions: async function () {
        try {
          const res = await API.employees.options();
          this.options = res.items;
        } catch (e) { /* 忽略 */ }
      },

      /* ------------------------------------------------ 详情 */
      openDetail: async function (row) {
        try {
          this.detail = await API.employees.get(row.id);
          this.showDetail = true;
        } catch (e) { App.toast(e.message, 'error'); }
      },

      /* ------------------------------------------------ 删除 */
      remove: async function (row) {
        const ok = await App.confirm({
          title: '删除员工',
          message: '确定要删除「' + row.name + '（' + row.emp_no + '）」吗？',
          detail: App.isAdmin()
            ? '删除后该员工的档案将不可恢复（考勤、报告等关联数据会一并清理）。'
            : '部门主管执行删除时，系统会将该员工标记为离职并保留历史记录。',
          danger: true, okText: '确认删除',
        });
        if (!ok) return;
        try {
          const res = await API.employees.remove(row.id);
          App.toast(res.message, 'success');
          this.load();
        } catch (e) { App.toast(e.message, 'error'); }
      },

      /* ------------------------------------------------ 批量 */
      batchStatus: async function () {
        if (!this.selected.length) return;
        const self = this;
        const status = prompt('要把选中的 ' + this.selected.length + ' 名员工状态改为？\n' +
          '可选：在职 / 试用期 / 休假 / 离职', '离职');
        if (!status) return;
        try {
          const res = await API.employees.batchStatus(this.selected, status.trim());
          App.toast(res.message, 'success');
          self.load();
        } catch (e) { App.toast(e.message, 'error'); }
      },
      batchDelete: async function () {
        if (!this.selected.length) return;
        const ok = await App.confirm({
          title: '批量删除',
          message: '确定要删除选中的 ' + this.selected.length + ' 名员工吗？',
          detail: '该操作不可恢复，仅系统管理员可执行。', danger: true, okText: '确认删除',
        });
        if (!ok) return;
        try {
          const res = await API.employees.batchDelete(this.selected);
          App.toast(res.message, 'success');
          this.load();
        } catch (e) { App.toast(e.message, 'error'); }
      },
      openAccountModal: function () {
        if (!this.selected.length) { App.toast('请先勾选员工', 'warning'); return; }
        this.accountResult = null;
        this.showAccount = true;
      },
      createAccounts: async function () {
        this.creatingAccounts = true;
        try {
          this.accountResult = await API.employees.createAccounts(
            this.selected, this.accountPwd, this.accountRole);
          App.toast(this.accountResult.message, 'success');
          this.load();
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.creatingAccounts = false; }
      },

      /* ------------------------------------------------ 导入导出 */
      exportExcel: async function () {
        try {
          const name = await API.download('/employees/export/excel', '员工名册.xlsx');
          App.toast('已导出：' + name, 'success');
        } catch (e) { App.toast(e.message, 'error'); }
      },
      downloadTemplate: async function () {
        try {
          await API.download('/employees/import/template', 'employee_import_template.xlsx');
          App.toast('模板已下载', 'success');
        } catch (e) { App.toast(e.message, 'error'); }
      },
      pickFile: function (e) {
        this.importFile = e.target.files[0] || null;
        this.importResult = null;
      },
      onDrop: function (e) {
        this.importFile = e.dataTransfer.files[0] || null;
        this.importResult = null;
      },
      doImport: async function () {
        if (!this.importFile) { App.toast('请先选择 Excel 文件', 'warning'); return; }
        this.importing = true;
        try {
          const fd = new FormData();
          fd.append('file', this.importFile);
          this.importResult = await API.employees.importFile(fd);
          App.toast(this.importResult.message, this.importResult.failed ? 'warning' : 'success');
          this.load();
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.importing = false; }
      },

      /* ------------------------------------------------ 小工具 */
      fmt: function (v) { return App.dateOnly(v); },
      money: function (v) { return v === null || v === undefined ? '—' : '¥' + App.money(v); },
      selectAllText: function () {
        return this.selected.length ? '已选 ' + this.selected.length + ' 人' : '';
      },
    },
    template: `
      <div>
        <!-- ================= 筛选栏 ================= -->
        <div class="card">
          <div class="filters">
            <input class="grow" type="text" v-model="query.keyword" @keyup.enter="search"
                   placeholder="搜索工号 / 姓名 / 手机号 / 职位 ...">
            <dept-select v-model="query.department_id" :depts="depts" placeholder="全部部门"
                         @update:modelValue="search"></dept-select>
            <select v-model="query.status" @change="search">
              <option value="">全部状态</option>
              <option v-for="s in statusList" :key="s" :value="s">{{ s }}</option>
            </select>
            <select v-model="query.gender" @change="search">
              <option value="">全部性别</option>
              <option value="男">男</option>
              <option value="女">女</option>
            </select>
            <select v-model="query.sort" @change="search">
              <option value="id_desc">最新添加优先</option>
              <option value="hire_date_desc">入职时间倒序</option>
              <option value="name_asc">按姓名排序</option>
            </select>
            <button class="btn primary" @click="search">🔍 查询</button>
            <button class="btn" @click="reset">重置</button>

            <div class="spacer"></div>

            <template v-if="canWrite">
              <button class="btn" @click="exportExcel">📤 导出 Excel</button>
              <button class="btn" @click="downloadTemplate">📋 导入模板</button>
              <button class="btn" @click="showImport = true; importResult = null">📥 批量导入</button>
              <button class="btn primary" @click="openCreate">➕ 新增员工</button>
            </template>
          </div>

          <!-- ================= 批量操作条 ================= -->
          <div class="filters" v-if="selected.length" style="background:#ebf4ff;border-bottom:1px solid #bee3f8">
            <span class="fs13"><b>{{ selectAllText() }}</b></span>
            <button class="btn sm" @click="batchStatus">批量改状态</button>
            <button class="btn sm" v-if="App.isAdmin()" @click="openAccountModal">🔑 批量开通账号</button>
            <button class="btn sm danger" v-if="App.isAdmin()" @click="batchDelete">批量删除</button>
            <button class="btn sm ghost" @click="selected = []">取消选择</button>
          </div>

          <!-- ================= 表格 ================= -->
          <div class="card-body tight">
            <loading v-if="loading"></loading>
            <empty-state v-else-if="!rows.length" icon="👥" text="没有找到符合条件的员工"
                         hint="换个关键词试试，或点击右上角新增员工">
              <button class="btn primary" v-if="canWrite" @click="openCreate">➕ 新增员工</button>
            </empty-state>
            <div class="table-wrap" v-else>
              <table class="data">
                <thead>
                  <tr>
                    <th class="checkbox-cell" v-if="canWrite">
                      <input type="checkbox" :checked="allChecked" @change="toggleAll">
                    </th>
                    <th>工号</th><th>姓名</th><th>部门</th><th>职位 / 职级</th>
                    <th>联系方式</th><th>状态</th><th>入职日期</th>
                    <th class="num" v-if="App.isAdmin()">月薪</th>
                    <th>账号</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in rows" :key="r.id"
                      :class="{ selected: selected.indexOf(r.id) >= 0 }">
                    <td class="checkbox-cell" v-if="canWrite">
                      <input type="checkbox" :checked="selected.indexOf(r.id) >= 0"
                             @change="toggleOne(r.id)">
                    </td>
                    <td class="mono">{{ r.emp_no }}</td>
                    <td>
                      <div class="flex-center gap1">
                        <span class="avatar" style="width:26px;height:26px;font-size:12px"
                              :style="{ background: App.avatarColor(r.name) }">{{ App.initials(r.name) }}</span>
                        <span class="strong link" @click="openDetail(r)">{{ r.name }}</span>
                      </div>
                    </td>
                    <td>
                      <span v-if="r.department_name">{{ r.department_name }}</span>
                      <span v-else class="text-light">未分配</span>
                    </td>
                    <td>
                      <div>{{ r.position || '—' }}</div>
                      <div class="fs12 text-light" v-if="r.job_level">{{ r.job_level }}</div>
                    </td>
                    <td>
                      <div class="fs12">{{ r.phone || '—' }}</div>
                      <div class="fs12 text-light">{{ r.email || '' }}</div>
                    </td>
                    <td><status-tag :status="r.status"></status-tag></td>
                    <td class="fs12 text-muted">{{ fmt(r.hire_date) }}</td>
                    <td class="num" v-if="App.isAdmin()">{{ money(r.salary) }}</td>
                    <td>
                      <span class="tag green" v-if="r.username">{{ r.username }}</span>
                      <span class="tag gray" v-else>未开通</span>
                    </td>
                    <td class="actions">
                      <button class="btn xs" @click="openDetail(r)">详情</button>
                      <button class="btn xs" v-if="canWrite" @click="openEdit(r)">编辑</button>
                      <button class="btn xs danger" v-if="canWrite" @click="remove(r)">删除</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <pagination v-if="!loading && rows.length" :page="page" :pages="pages" :total="total"
                      :size="size" @update:page="changePage" @update:size="changeSize"></pagination>
        </div>

        <!-- ================= 新增 / 编辑弹窗 ================= -->
        <modal v-if="showForm" :title="form.id ? '编辑员工' : '新增员工'"
               size="wide" :loading="saving" @close="showForm = false" @ok="save">
          <div class="form-grid c3">
            <div class="form-item">
              <label>姓名 <span class="req">*</span></label>
              <input type="text" v-model="form.name" placeholder="请输入姓名">
            </div>
            <div class="form-item">
              <label>工号</label>
              <input type="text" v-model="form.emp_no" placeholder="留空自动生成，如 EMP0027">
            </div>
            <div class="form-item">
              <label>性别</label>
              <select v-model="form.gender">
                <option>男</option><option>女</option><option>保密</option>
              </select>
            </div>

            <div class="form-item">
              <label>所属部门</label>
              <dept-select v-model="form.department_id" :depts="depts" placeholder="未分配"></dept-select>
            </div>
            <div class="form-item">
              <label>职位</label>
              <input type="text" v-model="form.position" placeholder="如 后端工程师">
            </div>
            <div class="form-item">
              <label>职级</label>
              <input type="text" v-model="form.job_level" placeholder="如 P6 / M2">
            </div>

            <div class="form-item">
              <label>员工状态</label>
              <select v-model="form.status">
                <option v-for="s in statusList" :key="s" :value="s">{{ s }}</option>
              </select>
            </div>
            <div class="form-item">
              <label>入职日期</label>
              <input type="date" v-model="form.hire_date">
            </div>
            <div class="form-item">
              <label>出生日期</label>
              <input type="date" v-model="form.birth_date">
            </div>

            <div class="form-item">
              <label>手机号</label>
              <input type="text" v-model="form.phone" placeholder="11 位手机号">
            </div>
            <div class="form-item">
              <label>邮箱</label>
              <input type="text" v-model="form.email" placeholder="name@company.com">
            </div>
            <div class="form-item" v-if="App.isAdmin()">
              <label>月薪（元）</label>
              <input type="number" v-model="form.salary" placeholder="仅管理员可见">
            </div>

            <div class="form-item">
              <label>学历</label>
              <select v-model="form.education">
                <option value="">未填写</option>
                <option>大专</option><option>本科</option><option>硕士</option><option>博士</option>
              </select>
            </div>
            <div class="form-item">
              <label>毕业院校</label>
              <input type="text" v-model="form.school">
            </div>
            <div class="form-item" v-if="App.isAdmin()">
              <label>身份证号</label>
              <input type="text" v-model="form.id_card" placeholder="仅管理员可见">
            </div>

            <div class="form-item">
              <label>紧急联系人</label>
              <input type="text" v-model="form.emergency_contact">
            </div>
            <div class="form-item">
              <label>紧急联系电话</label>
              <input type="text" v-model="form.emergency_phone">
            </div>
            <div class="form-item">
              <label>离职日期</label>
              <input type="date" v-model="form.leave_date" :disabled="form.status !== '离职'">
            </div>

            <div class="form-item full">
              <label>住址</label>
              <input type="text" v-model="form.address">
            </div>
            <div class="form-item full">
              <label>备注</label>
              <textarea v-model="form.remark" placeholder="其他需要记录的信息"></textarea>
            </div>
          </div>
        </modal>

        <!-- ================= 详情弹窗 ================= -->
        <modal v-if="showDetail && detail" :title="'员工详情 — ' + detail.name"
               size="wide" :hideFooter="true" @close="showDetail = false">
          <div class="flex-center gap2 mb2">
            <div class="avatar lg" :style="{ background: App.avatarColor(detail.name) }">
              {{ App.initials(detail.name) }}
            </div>
            <div>
              <div class="strong" style="font-size:17px">{{ detail.name }}
                <status-tag :status="detail.status" style="margin-left:6px"></status-tag>
              </div>
              <div class="fs12 text-muted mt1">
                {{ detail.emp_no }} · {{ detail.department_name || '未分配部门' }} ·
                {{ detail.position || '未填写职位' }}
              </div>
            </div>
          </div>
          <div class="info-list">
            <info-row label="性别" :value="detail.gender"></info-row>
            <info-row label="年龄" :value="detail.age ? detail.age + ' 岁' : ''"></info-row>
            <info-row label="手机号" :value="detail.phone"></info-row>
            <info-row label="邮箱" :value="detail.email"></info-row>
            <info-row label="职级" :value="detail.job_level"></info-row>
            <info-row label="入职日期" :value="fmt(detail.hire_date)"></info-row>
            <info-row label="学历" :value="detail.education"></info-row>
            <info-row label="毕业院校" :value="detail.school"></info-row>
            <info-row label="紧急联系人" :value="detail.emergency_contact"></info-row>
            <info-row label="紧急联系电话" :value="detail.emergency_phone"></info-row>
            <info-row label="登录账号" :value="detail.username || '未开通'"></info-row>
            <info-row label="离职日期" :value="fmt(detail.leave_date)"></info-row>
            <info-row v-if="App.isAdmin()" label="身份证号" :value="detail.id_card"></info-row>
            <info-row v-if="App.isAdmin()" label="月薪" :value="money(detail.salary)"></info-row>
            <info-row label="住址" :value="detail.address" full></info-row>
            <info-row label="备注" :value="detail.remark" full></info-row>
          </div>
        </modal>

        <!-- ================= 导入弹窗 ================= -->
        <modal v-if="showImport" title="批量导入员工" :loading="importing"
               okText="开始导入" @close="showImport = false" @ok="doImport">
          <div class="file-drop"
               @click="$refs.fileInput.click()"
               @dragover.prevent
               @drop.prevent="onDrop">
            <div class="icon">📥</div>
            <div>点击选择文件，或把 Excel 拖到这里</div>
            <div class="tip">仅支持 .xlsx 格式，建议先下载导入模板</div>
            <div class="fname" v-if="importFile">已选择：{{ importFile.name }}</div>
          </div>
          <input ref="fileInput" type="file" accept=".xlsx,.xlsm" style="display:none" @change="pickFile">
          <div class="fs12 text-muted mt2" style="line-height:1.9">
            · 必填列：<b>姓名</b>；工号留空会自动生成<br>
            · 部门名称必须与系统内已有部门完全一致，否则该行会被跳过<br>
            · 重复工号的行会被跳过，不会覆盖已有数据<br>
            · 部门主管只能向自己管辖的部门导入员工
          </div>
          <div v-if="importResult" class="mt2" style="background:#f7fafc;padding:12px;border-radius:8px">
            <div class="strong mb1">导入结果</div>
            <div class="fs13">成功 <b class="text-success">{{ importResult.created }}</b> 条，
              跳过 <b class="text-danger">{{ importResult.failed }}</b> 条</div>
            <ul class="fs12 text-muted mt1" style="padding-left:18px;max-height:180px;overflow:auto">
              <li v-for="(err, i) in importResult.errors" :key="i">{{ err }}</li>
            </ul>
          </div>
        </modal>

        <!-- ================= 批量开通账号 ================= -->
        <modal v-if="showAccount" title="批量为员工开通登录账号" :loading="creatingAccounts"
               okText="确认开通" @close="showAccount = false" @ok="createAccounts">
          <div class="form-grid c2">
            <div class="form-item">
              <label>用户名规则</label>
              <input type="text" value="员工工号（小写）" disabled>
              <span class="hint">如工号 EMP0027，则用户名为 emp0027</span>
            </div>
            <div class="form-item">
              <label>初始密码</label>
              <input type="text" v-model="accountPwd" placeholder="至少 6 位">
            </div>
            <div class="form-item">
              <label>账号角色</label>
              <select v-model="accountRole">
                <option value="employee">普通员工</option>
                <option value="manager">部门主管</option>
                <option value="admin">系统管理员</option>
              </select>
              <span class="hint">请谨慎授予管理员权限</span>
            </div>
          </div>
          <div class="fs12 text-muted mt2">
            将为已勾选的 {{ selected.length }} 名员工创建账号；已有账号或用户名被占用的员工会自动跳过。
          </div>
          <div v-if="accountResult" class="mt2" style="background:#f7fafc;padding:12px;border-radius:8px">
            <div class="fs13">成功创建 <b class="text-success">{{ accountResult.created.length }}</b> 个账号</div>
            <div class="fs12 text-muted mt1" v-if="accountResult.created.length">
              {{ accountResult.created.join('、') }}
            </div>
            <div class="fs12 text-warning mt1" v-if="accountResult.skipped.length">
              跳过：{{ accountResult.skipped.join('、') }}
            </div>
          </div>
        </modal>
      </div>`,
  };
})();
