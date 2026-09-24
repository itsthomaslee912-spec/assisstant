import { useEffect, useState } from "react";
import dayjs from "dayjs";
import { Button, Card, Col, DatePicker, Form, Input, Modal, Popconfirm, Row, Select, Space, Table, Tag, Typography, message } from "antd";
import { CalendarOutlined, DeleteOutlined, EditOutlined, FilterOutlined, LinkOutlined, PlusOutlined, SearchOutlined, UploadOutlined, UserOutlined } from "@ant-design/icons";
import { api } from "../api";
import type { Job, Page, Profile, User } from "../types";

const EMPTY: Page<Job> = { items: [], total: 0, page: 1, page_size: 10 };
const today = dayjs().format("YYYY-MM-DD");
const dateTime = (value: string | null) => value ? dayjs(value).format("MMM D, YYYY h:mm A") : "—";

export default function JobsPage({ user }: { user: User }) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useState<number>();
  const [data, setData] = useState(EMPTY);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [from, setFrom] = useState(today);
  const [to, setTo] = useState(today);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Job | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkText, setBulkText] = useState("");
  const [form] = Form.useForm();

  useEffect(() => {
    api.profileOptions().then(rows => {
      setProfiles(rows);
      if (rows.length) setProfileId(value => value || rows[0].id);
    }).catch(error => message.error(error.message));
  }, []);

  const load = () => {
    if (!profileId) return;
    setLoading(true);
    api.jobs(new URLSearchParams({ profile_id: String(profileId), status, date_from: from, date_to: to, search, page: String(page), page_size: "10" }))
      .then(setData).catch(error => message.error(error.message)).finally(() => setLoading(false));
  };
  useEffect(load, [profileId, status, from, to, search, page]);

  const edit = (job?: Job) => {
    setEditing(job || null);
    form.resetFields();
    form.setFieldsValue(job ? { ...job, application_date: dayjs(job.application_date) } : { profile_id: profileId, status: "pending", bot_check_status: "pending", work_model: "remote", application_date: dayjs() });
    setOpen(true);
  };
  const save = async () => {
    try {
      const values = await form.validateFields();
      await api.saveJob(editing?.id || null, { ...values, application_date: values.application_date.format("YYYY-MM-DD") });
      message.success(editing ? "Job updated" : "Job created"); setOpen(false); load();
    } catch (error) { if (error instanceof Error) message.error(error.message); }
  };
  const bidderUpdate = (job: Job, key: "status" | "work_model", value: string) => api.updateBidderJob(job.id, { status: key === "status" ? value : job.status, work_model: key === "work_model" ? value : job.work_model }).then(load).catch(error => message.error(error.message));
  const updateBotCheck = async (job: Job, next: "pending" | "pass" | "failure") => {
    setData(current => ({ ...current, items: current.items.map(item => item.id === job.id ? { ...item, bot_check_status: next } : item) }));
    try {
      await api.saveJob(job.id, {
        profile_id: job.profile_id, company_name: job.company_name, role: job.role,
        job_link: job.job_link, work_model: job.work_model, status: job.status,
        bot_check_status: next, application_date: job.application_date,
      });
    } catch (error) {
      setData(current => ({ ...current, items: current.items.map(item => item.id === job.id ? { ...item, bot_check_status: job.bot_check_status } : item) }));
      message.error(error instanceof Error ? error.message : "Unable to update bot check");
    }
  };
  const bulk = () => {
    if (!profileId) return;
    api.bulkJobs(profileId, bulkText).then(result => {
      message.success(`${result.created} jobs imported`);
      if (result.errors.length) message.warning(result.errors.slice(0, 3).join(" · "));
      setBulkOpen(false); setBulkText(""); load();
    }).catch(error => message.error(error.message));
  };
  const selectedProfile = profiles.find(profile => profile.id === profileId);

  return <div className="page-stack">
    {user.role === "admin" && <div className="page-heading jobs-heading actions-only"><Space wrap><Button className="secondary-action" icon={<UploadOutlined />} disabled={!profileId} onClick={() => setBulkOpen(true)}>Import jobs</Button><Button type="primary" icon={<PlusOutlined />} disabled={!profileId} onClick={() => edit()}>New application</Button></Space></div>}
    <Card className="content-card jobs-card" bordered={false}>
      <div className="profile-picker-block">
        <div className="profile-picker-icon"><UserOutlined /></div>
        <div className="profile-picker-copy"><Typography.Text type="secondary">Working profile</Typography.Text><Typography.Text strong>{selectedProfile ? `${selectedProfile.first_name} ${selectedProfile.last_name}` : "Choose a profile"}</Typography.Text></div>
        <Select className="profile-picker" showSearch optionFilterProp="label" value={profileId} onChange={value => { setPage(1); setProfileId(value); }} placeholder="Select profile" options={profiles.map(profile => ({ value: profile.id, label: `${profile.first_name} ${profile.last_name} · ${profile.email}` }))} />
      </div>
      <div className="filter-panel">
        <div className="filter-panel-title"><FilterOutlined /><span>Filters</span></div>
        <div className="table-toolbar jobs">
          <Select value={status} onChange={value => { setPage(1); setStatus(value); }} options={["all", "pending", "applied", "canceled"].map(value => ({ value, label: value === "all" ? "All statuses" : value[0].toUpperCase() + value.slice(1) }))} />
          <div className="date-field"><CalendarOutlined /><DatePicker value={dayjs(from)} onChange={value => { setPage(1); setFrom(value?.format("YYYY-MM-DD") || today); }} /></div>
          <span className="date-separator">to</span>
          <div className="date-field"><CalendarOutlined /><DatePicker value={dayjs(to)} onChange={value => { setPage(1); setTo(value?.format("YYYY-MM-DD") || today); }} /></div>
          <Input className="job-search" allowClear prefix={<SearchOutlined />} placeholder="Search company or role" value={search} onChange={event => { setPage(1); setSearch(event.target.value); }} />
        </div>
      </div>
      <div className="results-heading"><div><Typography.Title level={5}>Application activity</Typography.Title><Typography.Text type="secondary">{data.total} {data.total === 1 ? "record" : "records"} in this view</Typography.Text></div>{status !== "all" && <Tag className={`status-filter status-${status}`}>{status}</Tag>}</div>
      <Table className="basic-jobs-table" size="small" rowKey="id" loading={loading} dataSource={data.items} scroll={{ x: 1400 }} pagination={{ current: page, pageSize: 10, total: data.total, showSizeChanger: false, showTotal: count => `${count} applications`, onChange: setPage }} columns={[
        { title: "No.", width: 70, render: (_: unknown, _row: Job, index: number) => (page - 1) * 10 + index + 1 },
        { title: "Date", dataIndex: "application_date", width: 120 },
        { title: "Company", dataIndex: "company_name", render: value => <strong>{value}</strong> },
        { title: "Role", dataIndex: "role" },
        { title: "Job link", dataIndex: "job_link", minWidth: 240, render: value => value ? <a href={value} target="_blank" rel="noreferrer">Open job <LinkOutlined /></a> : "—" },
        { title: "Work model", dataIndex: "work_model", render: (value, row) => user.role === "bidder" ? <Select className={`badge-select work-model-${value}`} size="small" value={value} placeholder="Select" onChange={next => bidderUpdate(row, "work_model", next)} options={["on-site", "hybrid", "remote"].map(item => ({ value: item, label: item }))} /> : value ? <Tag className={`work-model-tag work-model-${value}`}>{value}</Tag> : "—" },
        { title: "Status", dataIndex: "status", render: (value, row) => user.role === "bidder" ? <Select className={`badge-select status-${value}`} size="small" value={value} onChange={next => bidderUpdate(row, "status", next)} options={["pending", "applied", "canceled"].map(item => ({ value: item, label: item }))} /> : <Tag className={`job-status status-${value}`}>{value}</Tag> },
        { title: "Bot check", dataIndex: "bot_check_status", width: 125, render: (value, row) => user.role === "admin" ? <Select className={`badge-select bot-check-${value}`} size="small" value={value} onChange={next => updateBotCheck(row, next)} options={[{value:"pending",label:"Pending"},{value:"pass",label:"Pass"},{value:"failure",label:"Failure"}]} /> : <Tag className={`bot-check-tag bot-check-${value}`}>{value}</Tag> },
        { title: "Created at", dataIndex: "created_at", width: 190, render: dateTime },
        { title: "Submitted at", dataIndex: "submitted_at", width: 190, render: dateTime },
        ...(user.role === "admin" ? [{ title: "Actions", key: "actions", fixed: "right" as const, width: 96, render: (_: unknown, row: Job) => <Space size={4}><Button type="text" size="small" aria-label="Edit job" title="Edit" icon={<EditOutlined />} onClick={() => edit(row)} /><Popconfirm title="Delete this job?" description="This action cannot be undone." onConfirm={() => api.deleteJob(row.id).then(load).catch(error => message.error(error.message))}><Button type="text" size="small" danger aria-label="Delete job" title="Delete" icon={<DeleteOutlined />} /></Popconfirm></Space> }] : []),
      ]} />
    </Card>
    <Modal open={open} title={editing ? "Edit job application" : "Create job application"} onCancel={() => setOpen(false)} onOk={save} destroyOnHidden><Form form={form} layout="vertical"><Form.Item name="profile_id" label="Profile" rules={[{ required: true }]}><Select options={profiles.map(profile => ({ value: profile.id, label: `${profile.first_name} ${profile.last_name}` }))} /></Form.Item><Row gutter={16}><Col xs={24} sm={12}><Form.Item name="company_name" label="Company name" rules={[{ required: true }]}><Input /></Form.Item></Col><Col xs={24} sm={12}><Form.Item name="role" label="Role" rules={[{ required: true }]}><Input /></Form.Item></Col></Row><Form.Item name="job_link" label="Job link"><Input /></Form.Item><Row gutter={16}><Col xs={24} sm={6}><Form.Item name="work_model" label="Work model"><Select options={["on-site", "hybrid", "remote"].map(value => ({ value }))} /></Form.Item></Col><Col xs={24} sm={6}><Form.Item name="status" label="Status"><Select disabled={!editing} options={["pending", "applied", "canceled"].map(value => ({ value }))} /></Form.Item></Col><Col xs={24} sm={6}><Form.Item name="bot_check_status" label="Bot check"><Select disabled={!editing} options={["pending", "pass", "failure"].map(value => ({ value }))} /></Form.Item></Col><Col xs={24} sm={6}><Form.Item name="application_date" label="Date"><DatePicker style={{ width: "100%" }} /></Form.Item></Col></Row></Form></Modal>
    <Modal open={bulkOpen} title="Import job applications" onCancel={() => setBulkOpen(false)} onOk={bulk} okText="Import jobs"><Typography.Paragraph type="secondary">Paste one job per line: Company, Role, Job link, then optional Status and Work model. Use tabs or pipes. Status accepts Pending, Applied, or Canceled; Work model accepts Remote, Hybrid, or On-site.</Typography.Paragraph><Input.TextArea rows={9} value={bulkText} onChange={event => setBulkText(event.target.value)} placeholder={"Docusign\tLead AI Solutions Delivery Engineer\thttps://careers.example.com/job\tApplied"} /></Modal>
  </div>;
}
