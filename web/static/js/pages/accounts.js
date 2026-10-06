/* ==========================================================================
   账号管理（仅系统管理员）：登录账号、角色、状态、密码重置
   ========================================================================== */
(function () {
  'use strict';

  window.PageAccounts = {
    data: function () {
      return {
        loading: true,
        rows: [], total: 0, page: 1, size: 20, pages: 1,
        query: { keyword: '', role: '', department_id: null, is_active: '' },
        depts: [], employees: [],

        showForm: false, saving: false,
        form: { id: null, username: '', password: '', real_name: '', role: 'employee',
                department_id: null, phone: '', email: '', is_active: true },

        showReset: false, resetting: false, resetTarget: null, resetPwd: '',

        showLink: false, linkTarget: null, linkEmployeeId: null,
      };
    },
    computed: {
      roleOptions: function () {
        return [
          { value: 'boss', label: '老板', desc: '与系统管理员同权，可直接开除员工' },
          { value: 'admin', label: '系统管理员', desc: '拥有全部权限（系统维护用）' },
          { value: 'manager', label: '部门主管', desc: '可管理本部门及下级部门数据' },
          { value: 'employee', label: '普通员工', desc: '只能看本人相关数据' },
        ];
      },
    },
    mounted: function () { this.init(); },
    methods: {
      init: async function () {
        try {
          const [d, e] = await Promise.all([API.departments.list(), API.employees.options()]);
          this.depts = d.items;
          this.employees = e.items;
        } catch (err) { /* 忽略 */ }
        this.load();
      },
      load: async function () {
        this.loading = true;
        try {
          const params = Object.assign({ page: this.page, size: this.size }, this.query);
          if (params.is_active === '') delete params.is_active;
          else params.is_active = params.is_active === 'true';
          const res = await API.auth.users(params);
          this.rows = res.items;
          this.total = res.total;
          this.pages = res.pages;
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.loading = false; }
      },
      search: function () { this.page = 1; this.load(); },
      reset: function () {
        this.query = { keyword: '', role: '', department_id: null, is_active: '' };
        this.search();
      },
      changePage: function (p) { this.page = p; this.load(); },
      changeSize: function (s) { this.size = s; this.page = 1; this.load(); },

      openCreate: function () {
        this.form = { id: null, username: '', password: '123456', real_name: '',
                      role: 'employee', department_id: null, phone: '', email: '', is_active: true };
        this.showForm = true;
      },
      openEdit: function (row) {
        this.form = { id: row.id, username: row.username, password: '', real_name: row.real_name,
                      role: row.role, department_id: row.department_id, phone: row.phone || '',
                      email: row.email || '', is_active: row.is_active };
        this.showForm = true;
      },
      save: async function () {
        if (!this.form.real_name.trim()) { App.toast('请填写姓名', 'error'); return; }
        this.saving = true;
        try {
          if (this.form.id) {
            await API.auth.updateUser(this.form.id, {
              real_name: this.form.real_name, role: this.form.role,
              department_id: this.form.department_id, phone: this.form.phone,
              email: this.form.email, is_active: this.form.is_active,
            });
            App.toast('账号已更新', 'success');
          } else {
            if (!this.form.username.trim()) { App.toast('请填写登录用户名', 'error'); this.saving = false; return; }
            if ((this.form.password || '').length < 6) {
              App.toast('初始密码至少 6 位', 'error'); this.saving = false; return;
            }
            await API.auth.createUser({
              username: this.form.username, password: this.form.password,
              real_name: this.form.real_name, role: this.form.role,
              department_id: this.form.department_id, phone: this.form.phone,
              email: this.form.email,
            });
            App.toast('账号已创建', 'success');
          }
          this.showForm = false;
          this.load();
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.saving = false; }
      },
      openReset: function (row) {
        this.resetTarget = row;
        this.resetPwd = '123456';
        this.showReset = true;
      },
      doReset: async function () {
        if ((this.resetPwd || '').length < 6) { App.toast('密码至少 6 位', 'error'); return; }
        this.resetting = true;
        try {
          const res = await API.auth.resetPassword(this.resetTarget.id, this.resetPwd);
          App.toast(res.message + '，新密码：' + this.resetPwd, 'success');
          this.showReset = false;
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.resetting = false; }
      },
      remove: async function (row) {
        const ok = await App.confirm({
          title: '删除账号',
          message: '确定要删除账号「' + row.username + '（' + row.real_name + '）」吗？',
          detail: '该员工档案会保留，仅解除登录绑定；删除后对方将无法登录系统。',
          danger: true, okText: '确认删除',
        });
        if (!ok) return;
        try {
          const res = await API.auth.deleteUser(row.id);
          App.toast(res.message, 'success');
          this.load();
        } catch (e) { App.toast(e.message, 'error'); }
      },
      toggleActive: async function (row) {
        try {
          await API.auth.updateUser(row.id, { is_active: !row.is_active });
          App.toast(row.is_active ? '账号已停用' : '账号已启用', 'success');
          this.load();
        } catch (e) { App.toast(e.message, 'error'); }
      },

      openLink: function (row) {
        this.linkTarget = row;
        this.linkEmployeeId = null;
        this.showLink = true;
      },
      doLink: async function () {
        if (!this.linkEmployeeId) { App.toast('请选择要绑定的员工', 'warning'); return; }
        try {
          const res = await API.employees.linkAccount(this.linkEmployeeId, this.linkTarget.id);
          App.toast(res.message, 'success');
          this.showLink = false;
          this.load();
        } catch (e) { App.toast(e.message, 'error'); }
      },

      fmt: function (v) { return App.dateTime(v); },
      initials: function (name) { return App.initials(name); },
    },
    template: `
      <div>
        <div class="grid c4 mb2">
          <stat-card label="账号总数" :value="total" foot="系统内全部登录账号" accent="1" icon="🔑"></stat-card>
          <stat-card label="老板 / 管理员"
                     :value="rows.filter(function(r){return r.role==='admin'||r.role==='boss'}).length"
                     foot="最高权限角色（当前页统计）" accent="5" icon="👑"></stat-card>
          <stat-card label="部门主管" :value="rows.filter(function(r){return r.role==='manager'}).length"
                     foot="当前页统计" accent="3" icon="👔"></stat-card>
          <stat-card label="已停用" :value="rows.filter(function(r){return !r.is_active}).length"
                     foot="当前页统计" accent="4" icon="🚫"></stat-card>
        </div>

        <div class="card">
          <div class="filters">
            <input class="grow" type="text" v-model="query.keyword" @keyup.enter="search"
                   placeholder="搜索用户名或姓名 ...">
            <select v-model="query.role" @change="search">
              <option value="">全部角色</option>
              <option value="boss">老板</option>
              <option value="admin">系统管理员</option>
              <option value="manager">部门主管</option>
              <option value="employee">普通员工</option>
            </select>
            <dept-select v-model="query.department_id" :depts="depts" placeholder="全部部门"
                         @update:modelValue="search"></dept-select>
            <select v-model="query.is_active" @change="search">
              <option value="">全部状态</option>
              <option value="true">已启用</option>
              <option value="false">已停用</option>
            </select>
            <button class="btn primary" @click="search">🔍 查询</button>
            <button class="btn" @click="reset">重置</button>
            <div class="spacer"></div>
            <button class="btn primary" @click="openCreate">➕ 新建账号</button>
          </div>

          <div class="card-body tight">
            <loading v-if="loading"></loading>
            <empty-state v-else-if="!rows.length" icon="🔑" text="没有符合条件的账号"></empty-state>
            <div class="table-wrap" v-else>
              <table class="data">
                <thead>
                  <tr><th>用户名</th><th>姓名</th><th>角色</th><th>部门</th>
                    <th>联系方式</th><th>状态</th><th>最近登录</th><th></th></tr>
                </thead>
                <tbody>
                  <tr v-for="r in rows" :key="r.id">
                    <td>
                      <div class="flex-center gap1">
                        <span class="avatar" style="width:26px;height:26px;font-size:12px"
                              :style="{ background: App.avatarColor(r.real_name) }">
                          {{ initials(r.real_name) }}
                        </span>
                        <span class="mono strong">{{ r.username }}</span>
                        <span class="tag red" v-if="App.user && r.id === App.user.id">当前</span>
                      </div>
                    </td>
                    <td>{{ r.real_name }}</td>
                    <td>
                      <span class="tag" :class="{ boss: 'purple', admin: 'red',
                                                  manager: 'yellow', employee: 'blue' }[r.role]">
                        {{ r.role_label || App.roleLabel(r.role) }}
                      </span>
                    </td>
                    <td class="fs12">{{ r.department_name || '—' }}</td>
                    <td class="fs12">
                      <div>{{ r.phone || '—' }}</div>
                      <div class="text-light">{{ r.email || '' }}</div>
                    </td>
                    <td>
                      <span class="tag" :class="r.is_active ? 'green' : 'gray'">
                        {{ r.is_active ? '启用' : '停用' }}
                      </span>
                    </td>
                    <td class="fs12 text-muted">{{ fmt(r.last_login_at) }}</td>
                    <td class="actions">
                      <button class="btn xs" @click="openEdit(r)">编辑</button>
                      <button class="btn xs" @click="openReset(r)">重置密码</button>
                      <button class="btn xs" @click="toggleActive(r)"
                              v-if="!App.user || r.id !== App.user.id">
                        {{ r.is_active ? '停用' : '启用' }}
                      </button>
                      <button class="btn xs danger" @click="remove(r)"
                              v-if="!App.user || r.id !== App.user.id">删除</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <pagination v-if="!loading && rows.length" :page="page" :pages="pages" :total="total"
                      :size="size" @update:page="changePage" @update:size="changeSize"></pagination>
        </div>

        <!-- ================= 新建 / 编辑账号 ================= -->
        <modal v-if="showForm" :title="form.id ? '编辑账号' : '新建登录账号'"
               :loading="saving" @close="showForm = false" @ok="save">
          <div class="form-grid c2">
            <div class="form-item">
              <label>登录用户名 <span class="req">*</span></label>
              <input type="text" v-model="form.username" :disabled="!!form.id"
                     placeholder="建议用工号，如 emp0027">
              <span class="hint" v-if="form.id">用户名创建后不可修改</span>
            </div>
            <div class="form-item" v-if="!form.id">
              <label>初始密码 <span class="req">*</span></label>
              <input type="text" v-model="form.password" placeholder="至少 6 位">
            </div>
            <div class="form-item">
              <label>姓名 <span class="req">*</span></label>
              <input type="text" v-model="form.real_name">
            </div>
            <div class="form-item">
              <label>账号角色</label>
              <select v-model="form.role">
                <option v-for="o in roleOptions" :key="o.value" :value="o.value">
                  {{ o.label }} —— {{ o.desc }}
                </option>
              </select>
            </div>
            <div class="form-item">
              <label>所属部门</label>
              <dept-select v-model="form.department_id" :depts="depts" placeholder="未分配"></dept-select>
            </div>
            <div class="form-item">
              <label>手机号</label>
              <input type="text" v-model="form.phone">
            </div>
            <div class="form-item">
              <label>邮箱</label>
              <input type="text" v-model="form.email">
            </div>
            <div class="form-item" v-if="form.id">
              <label>账号状态</label>
              <select v-model="form.is_active">
                <option :value="true">启用</option>
                <option :value="false">停用</option>
              </select>
            </div>
          </div>
          <div class="fs12 text-muted mt2">
            角色决定数据范围：管理员看全公司，主管看本部门及下级部门，普通员工只看本人相关数据。
          </div>
        </modal>

        <!-- ================= 重置密码 ================= -->
        <modal v-if="showReset" title="重置登录密码" size="narrow" :loading="resetting"
               okText="确认重置" @close="showReset = false" @ok="doReset">
          <div class="fs13 mb2">
            账号：<b class="mono">{{ resetTarget ? resetTarget.username : '' }}</b>
            （{{ resetTarget ? resetTarget.real_name : '' }}）
          </div>
          <div class="form-item">
            <label>新密码</label>
            <input type="text" v-model="resetPwd" placeholder="至少 6 位">
            <span class="hint">重置后请通过安全渠道告知本人，并提醒其尽快自行修改</span>
          </div>
        </modal>

        <!-- ================= 绑定员工 ================= -->
        <modal v-if="showLink" title="绑定员工档案" :hideFooter="true" @close="showLink = false">
          <div class="fs13 mb2">
            将账号 <b class="mono">{{ linkTarget ? linkTarget.username : '' }}</b>
            绑定到某位员工，绑定后该员工即可打卡、提交请假、上传报告。
          </div>
          <div class="form-item mb2">
            <label>选择员工</label>
            <select v-model="linkEmployeeId">
              <option :value="null">请选择员工</option>
              <option v-for="e in employees" :key="e.id" :value="e.id">
                {{ e.name }} · {{ e.emp_no }}{{ e.department_name ? ' · ' + e.department_name : '' }}
                {{ e.user_id ? '（已绑定其他账号）' : '' }}
              </option>
            </select>
          </div>
          <div class="flex-between">
            <span class="fs12 text-muted"></span>
            <div class="btn-group">
              <button class="btn" @click="showLink = false">取消</button>
              <button class="btn primary" @click="doLink">确认绑定</button>
            </div>
          </div>
        </modal>
      </div>`,
  };
})();
