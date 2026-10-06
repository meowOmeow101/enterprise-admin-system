/* ==========================================================================
   部门与组织架构：树形展示、人员归属、主管设置
   ========================================================================== */
(function () {
  'use strict';

  const EMPTY_FORM = function () {
    return { id: null, name: '', code: '', parent_id: null, manager_id: null,
             description: '', sort_order: 0 };
  };

  window.PageDepartments = {
    data: function () {
      return {
        loading: true,
        tree: [], flat: [],
        employees: [],
        expanded: {},
        showForm: false, saving: false, form: EMPTY_FORM(),
        showMembers: false, memberDept: null, memberList: [],
        orgLoading: false, orgChart: [],
      };
    },
    computed: {
      canWrite: function () { return App.isManager(); },
      totalMembers: function () {
        return this.flat.reduce(function (sum, d) { return sum + (d.member_count || 0); }, 0);
      },
    },
    mounted: function () { this.init(); },
    methods: {
      init: async function () {
        try {
          const res = await API.employees.options();
          this.employees = res.items;
        } catch (e) { /* 忽略 */ }
        await this.load();
      },
      load: async function () {
        this.loading = true;
        try {
          const res = await API.departments.tree();
          this.tree = res.tree;
          this.flat = res.items;
          // 默认展开全部一级部门
          const self = this;
          this.tree.forEach(function (d) { self.expanded[d.id] = true; });
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.loading = false; }
      },
      toggle: function (id) { this.expanded[id] = !this.expanded[id]; },
      expandAll: function () {
        const self = this;
        this.flat.forEach(function (d) { self.expanded[d.id] = true; });
      },
      collapseAll: function () { this.expanded = {}; },

      openCreate: function (parent) {
        this.form = EMPTY_FORM();
        if (parent) this.form.parent_id = parent.id;
        this.showForm = true;
      },
      openEdit: function (dept) {
        this.form = {
          id: dept.id, name: dept.name, code: dept.code || '',
          parent_id: dept.parent_id, manager_id: dept.manager_id,
          description: dept.description || '', sort_order: dept.sort_order || 0,
        };
        this.showForm = true;
      },
      save: async function () {
        if (!this.form.name) { App.toast('请填写部门名称', 'error'); return; }
        this.saving = true;
        try {
          const payload = {
            name: this.form.name, code: this.form.code || null,
            parent_id: this.form.parent_id, manager_id: this.form.manager_id,
            description: this.form.description, sort_order: App.num(this.form.sort_order),
          };
          if (this.form.id) {
            await API.departments.update(this.form.id, payload);
            App.toast('部门已更新', 'success');
          } else {
            await API.departments.create(payload);
            App.toast('部门已创建', 'success');
          }
          this.showForm = false;
          this.load();
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.saving = false; }
      },
      remove: async function (dept) {
        const ok = await App.confirm({
          title: '删除部门',
          message: '确定要删除部门「' + dept.name + '」吗？',
          detail: '若该部门下仍有子部门或在职员工，系统会拒绝删除并提示你先处理。',
          danger: true, okText: '确认删除',
        });
        if (!ok) return;
        try {
          const res = await API.departments.remove(dept.id);
          App.toast(res.message, 'success');
          this.load();
        } catch (e) { App.toast(e.message, 'error'); }
      },

      showMembersOf: async function (dept) {
        this.memberDept = dept;
        this.showMembers = true;
        try {
          const res = await API.employees.list({ department_id: dept.id, size: 200, status: '' });
          this.memberList = res.items;
        } catch (e) { App.toast(e.message, 'error'); this.memberList = []; }
      },

      loadOrgChart: async function () {
        this.orgLoading = true;
        try {
          const res = await API.dashboard.orgChart();
          this.orgChart = res.items;
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.orgLoading = false; }
      },

      childCount: function (dept) { return (dept.children || []).length; },
      fmt: function (v) { return App.dateOnly(v); },
    },
    template: `
      <div>
        <!-- ================= 概览 ================= -->
        <div class="grid c3 mb2">
          <stat-card label="部门数量" :value="flat.length" foot="含各级子部门" accent="1" icon="🏢"></stat-card>
          <stat-card label="在职员工" :value="totalMembers" foot="已分配到部门的在职人数"
                     accent="2" icon="👥"></stat-card>
          <stat-card label="一级部门" :value="tree.length" foot="直接向公司汇报的部门"
                     accent="4" icon="🏛️"></stat-card>
        </div>

        <div class="card">
          <div class="card-head">
            <h3>组织架构</h3>
            <span class="sub">点击部门名可查看该部门在职员工</span>
            <button class="btn sm" @click="expandAll">全部展开</button>
            <button class="btn sm" @click="collapseAll">全部收起</button>
            <button class="btn sm primary" v-if="canWrite" @click="openCreate(null)">
              ➕ 新建一级部门
            </button>
          </div>

          <div class="card-body">
            <loading v-if="loading"></loading>
            <empty-state v-else-if="!tree.length" icon="🏢" text="还没有部门"
                         hint="建议先按公司实际架构建好部门，再录入员工">
              <button class="btn primary" v-if="canWrite" @click="openCreate(null)">➕ 新建部门</button>
            </empty-state>

            <template v-else>
              <!-- 一级部门循环，内部用递归模板展开子部门 -->
              <div v-for="dept in tree" :key="dept.id" style="margin-bottom:10px">
                <div class="card" style="margin:0;border-radius:10px">
                  <div class="card-body" style="padding:14px 16px">
                    <div class="flex-between wrap gap2">
                      <div class="flex-center gap1">
                        <span style="cursor:pointer;width:16px;color:#94a3b8"
                              v-if="childCount(dept)"
                              @click="toggle(dept.id)">
                          {{ expanded[dept.id] ? '▾' : '▸' }}
                        </span>
                        <span v-else style="width:16px"></span>
                        <span style="font-size:16px">🏢</span>
                        <div>
                          <span class="strong link" style="font-size:14.5px"
                                @click="showMembersOf(dept)">{{ dept.name }}</span>
                          <span class="tag outline mono" style="margin-left:6px" v-if="dept.code">
                            {{ dept.code }}
                          </span>
                          <div class="fs12 text-light mt1">
                            主管：{{ dept.manager_name || '未指定' }}
                            <span v-if="childCount(dept)"> · {{ childCount(dept) }} 个子部门</span>
                            · 创建于 {{ fmt(dept.created_at) }}
                          </div>
                        </div>
                      </div>
                      <div class="flex-center gap1">
                        <span class="tag green">{{ dept.member_count }} 人</span>
                        <button class="btn xs" @click="showMembersOf(dept)">成员</button>
                        <template v-if="canWrite">
                          <button class="btn xs" @click="openCreate(dept)">➕ 子部门</button>
                          <button class="btn xs" @click="openEdit(dept)">编辑</button>
                          <button class="btn xs danger" @click="remove(dept)">删除</button>
                        </template>
                      </div>
                    </div>
                    <div class="fs12 text-muted mt1" v-if="dept.description">{{ dept.description }}</div>
                  </div>

                  <!-- 子部门列表 -->
                  <div v-if="expanded[dept.id] && childCount(dept)"
                       style="border-top:1px solid var(--border);padding:10px 16px 12px;background:#fcfdfe">
                    <div v-for="child in dept.children" :key="child.id"
                         class="flex-between wrap gap1"
                         style="padding:9px 12px;border-radius:8px;margin-bottom:6px;background:#fff;
                                border:1px solid var(--border)">
                      <div class="flex-center gap1">
                        <span style="font-size:14px">📂</span>
                        <div>
                          <span class="strong link" @click="showMembersOf(child)">{{ child.name }}</span>
                          <span class="tag outline mono" style="margin-left:6px" v-if="child.code">
                            {{ child.code }}
                          </span>
                          <div class="fs12 text-light">
                            主管：{{ child.manager_name || '未指定' }}
                          </div>
                        </div>
                      </div>
                      <div class="flex-center gap1">
                        <span class="tag green">{{ child.member_count }} 人</span>
                        <button class="btn xs" @click="showMembersOf(child)">成员</button>
                        <template v-if="canWrite">
                          <button class="btn xs" @click="openEdit(child)">编辑</button>
                          <button class="btn xs danger" @click="remove(child)">删除</button>
                        </template>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- ================= 部门表单 ================= -->
        <modal v-if="showForm" :title="form.id ? '编辑部门' : '新建部门'"
               :loading="saving" @close="showForm = false" @ok="save">
          <div class="form-grid c2">
            <div class="form-item">
              <label>部门名称 <span class="req">*</span></label>
              <input type="text" v-model="form.name" placeholder="如 技术部">
            </div>
            <div class="form-item">
              <label>部门编码</label>
              <input type="text" v-model="form.code" placeholder="如 TECH，需唯一">
            </div>
            <div class="form-item">
              <label>上级部门</label>
              <dept-select v-model="form.parent_id" :depts="flat" placeholder="无（一级部门）"></dept-select>
            </div>
            <div class="form-item">
              <label>部门主管</label>
              <select v-model="form.manager_id">
                <option :value="null">暂不指定</option>
                <option v-for="e in employees" :key="e.id" :value="e.id">
                  {{ e.name }}{{ e.department_name ? '（' + e.department_name + '）' : '' }}
                </option>
              </select>
            </div>
            <div class="form-item">
              <label>排序值</label>
              <input type="number" v-model="form.sort_order" placeholder="数字越小越靠前">
            </div>
            <div class="form-item full">
              <label>部门说明</label>
              <textarea v-model="form.description" placeholder="部门职责说明"></textarea>
            </div>
          </div>
          <div class="fs12 text-muted mt2">
            提示：给部门指定主管后，该主管账号登录即拥有本部门及下级部门的数据管理权限。
          </div>
        </modal>

        <!-- ================= 部门成员 ================= -->
        <modal v-if="showMembers" :title="'部门成员 — ' + (memberDept ? memberDept.name : '')"
               size="wide" :hideFooter="true" @close="showMembers = false">
          <div class="table-wrap" v-if="memberList.length">
            <table class="data">
              <thead>
                <tr><th>姓名</th><th>工号</th><th>职位</th><th>状态</th>
                  <th>手机号</th><th>入职日期</th></tr>
              </thead>
              <tbody>
                <tr v-for="e in memberList" :key="e.id">
                  <td class="strong">{{ e.name }}</td>
                  <td class="mono">{{ e.emp_no }}</td>
                  <td>{{ e.position || '—' }}</td>
                  <td><status-tag :status="e.status"></status-tag></td>
                  <td class="fs12">{{ e.phone || '—' }}</td>
                  <td class="fs12 text-muted">{{ fmt(e.hire_date) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <empty-state v-else icon="👥" text="该部门下暂无在职员工"></empty-state>
        </modal>
      </div>`,
  };
})();
