import { useEffect, useState } from "react";
import dayjs from "dayjs";
import { Alert, Card, Col, DatePicker, Empty, Row, Skeleton, Statistic, Tabs, Typography } from "antd";
import { CheckCircleOutlined, SafetyCertificateOutlined, TeamOutlined, UserOutlined } from "@ant-design/icons";
import { api } from "../api";
import LineChart from "../components/LineChart";
import BarChart from "../components/BarChart";
import type { AdminDashboard, BidderDashboard, User } from "../types";

export default function DashboardPage({ user }: { user: User }) {
  const today = dayjs().format("YYYY-MM-DD");
  const [from, setFrom] = useState(today);
  const [to, setTo] = useState(today);
  const [admin, setAdmin] = useState<AdminDashboard | null>(null);
  const [bidder, setBidder] = useState<BidderDashboard | null>(null);
  const [profileId, setProfileId] = useState<number>();
  const [error, setError] = useState("");
  useEffect(() => {
    setError("");
    (user.role === "admin" ? api.adminDashboard(from, to).then(setAdmin) : api.bidderDashboard(profileId, from, to).then(setBidder)).catch((err) => setError(err.message));
  }, [user.role, from, to, profileId]);
  useEffect(() => {
    const profiles = user.role === "admin" ? admin?.profiles : bidder?.profiles;
    if (!profileId && profiles?.length) setProfileId(profiles[0].id);
  }, [admin, bidder, profileId, user.role]);
  if (error) return <Alert type="error" showIcon message={error} />;
  if (user.role === "admin" && !admin || user.role === "bidder" && !bidder) return <Skeleton active />;
  const dateControls = <div className="dashboard-date-range"><label><span>From</span><DatePicker value={dayjs(from)} onChange={value=>{const next=value?.format("YYYY-MM-DD")||today;setFrom(next);if(next>to)setTo(next)}} /></label><label><span>To</span><DatePicker value={dayjs(to)} onChange={value=>{const next=value?.format("YYYY-MM-DD")||today;setTo(next);if(next<from)setFrom(next)}} /></label></div>;
  const chart = (data: {label:string;value:number}[]) => from === to ? <LineChart data={data} /> : <BarChart data={data} />;
  if (admin) return <div className="page-stack">
    <div className="page-heading actions-only">{dateControls}</div>
    <Row gutter={[16,16]}>
      <Col xs={24} sm={12} xl={8}><Card className="metric-card"><Statistic title="Profiles" value={admin.total_profiles} prefix={<UserOutlined />} /></Card></Col>
      <Col xs={24} sm={12} xl={8}><Card className="metric-card"><Statistic title="Active bidders" value={admin.active_bidders} prefix={<TeamOutlined />} /></Card></Col>
      <Col xs={24} sm={12} xl={8}><Card className="metric-card"><Statistic title="Applications in period" value={admin.applications_count} prefix={<CheckCircleOutlined />} /></Card></Col>
    </Row>
    <Card title="Application activity by profile" className="content-card">
      {admin.profiles.length ? <Tabs activeKey={profileId?String(profileId):undefined} onChange={(key)=>setProfileId(Number(key))} items={admin.profiles.map((profile) => ({ key:String(profile.id), label:`${profile.first_name} ${profile.last_name}`, children:chart(admin.profile_series[String(profile.id)]||[]) }))} /> : <Empty description="Create profiles to begin tracking activity" />}
    </Card>
    <div><Typography.Title level={4}>Active bidder payments</Typography.Title><Row gutter={[16,16]}>{admin.pay_cards.map((item) => <Col xs={24} md={12} xl={8} key={item.user_id}><Card className="pay-card"><Typography.Text type="secondary">{item.bidder_name}</Typography.Text><Typography.Title level={3}>${Number(item.paid_amount).toFixed(2)}</Typography.Title><Typography.Text>{item.bot_check_pass_count} bot checks passed × ${Number(item.per_bid_pay_amount).toFixed(2)}</Typography.Text></Card></Col>)}</Row></div>
  </div>;
  return <div className="page-stack">
    <div className="page-heading"><div><Typography.Title level={2}>My performance</Typography.Title><Typography.Text type="secondary">Track daily activity and earnings for assigned profiles.</Typography.Text></div>{dateControls}</div>
    <Row gutter={[16,16]}><Col xs={24} md={8}><Card className="metric-card"><Statistic title="Applied jobs" value={bidder!.applied_count} prefix={<CheckCircleOutlined />} /></Card></Col><Col xs={24} md={8}><Card className="metric-card"><Statistic title="Bot Check Pass Count" value={bidder!.bot_check_pass_count} prefix={<SafetyCertificateOutlined />} /></Card></Col><Col xs={24} md={8}><Card className="metric-card"><Statistic title="Paid amount" value={bidder!.paid_amount} precision={2} prefix="$" /></Card></Col></Row>
    <Card className="content-card">{bidder!.profiles.length?<Tabs activeKey={profileId?String(profileId):undefined} onChange={(key) => setProfileId(Number(key))} items={bidder!.profiles.map((profile) => ({key:String(profile.id),label:`${profile.first_name} ${profile.last_name}`,children:chart(bidder!.series)}))}/>:<Empty description="No profiles have been assigned to you"/>}</Card>
  </div>;
}
