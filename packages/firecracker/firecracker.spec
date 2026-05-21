%global _dwz_low_mem_die_limit 0
%global debug_package %{nil}
%undefine cross_check_fips

Name: %{_cross_os}firecracker
Version: 1.15.1
Release: 1%{?dist}
Summary: Secure and fast microVMs for serverless computing
License: Apache-2.0
URL: https://github.com/firecracker-microvm/firecracker
Source0: https://github.com/firecracker-microvm/firecracker/archive/refs/tags/v%{version}.tar.gz
Source1: bundled-v%{version}.tar.gz

Source101: firecracker-sysusers.conf
Source200: vmlinux-5.10.225
Source201: test-rootfs.ext4

BuildRequires: %{_cross_os}glibc-devel
BuildRequires: %{_cross_os}libseccomp-devel

Requires: %{_cross_os}jailer

%description
%{summary}.

%package -n %{_cross_os}jailer
Summary: Jailer for Firecracker microVMs

%description -n %{_cross_os}jailer
%{summary}.

%prep
%setup -n firecracker-%{version} -q
%setup -T -D -a 1 -n firecracker-%{version}
%cargo_prep

%build
# LIBRARY_PATH needed for seccompiler build.rs which links libseccomp on the host
export LIBRARY_PATH=%{_cross_libdir}
%cargo_build_static -p firecracker
%cargo_build_static -p jailer

%install
install -d %{buildroot}%{_cross_bindir}
install -p -m 0755 %{__cargo_outdir_static}/firecracker %{buildroot}%{_cross_bindir}/firecracker
install -p -m 0755 %{__cargo_outdir_static}/jailer %{buildroot}%{_cross_bindir}/jailer



install -d %{buildroot}%{_cross_sysusersdir}
install -p -m 0644 %{S:101} %{buildroot}%{_cross_sysusersdir}/firecracker.conf

install -d %{buildroot}%{_cross_datadir}/firecracker/test
install -p -m 0644 %{S:200} %{buildroot}%{_cross_datadir}/firecracker/test/vmlinux
install -p -m 0644 %{S:201} %{buildroot}%{_cross_datadir}/firecracker/test/rootfs.ext4

%files
%license LICENSE NOTICE
%{_cross_attribution_file}
%{_cross_bindir}/firecracker
%dir %{_cross_datadir}/firecracker
%{_cross_datadir}/firecracker/test

%files -n %{_cross_os}jailer
%license LICENSE NOTICE
%{_cross_attribution_file}
%{_cross_bindir}/jailer
%{_cross_sysusersdir}/firecracker.conf

%changelog
