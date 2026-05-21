%undefine _debugsource_packages
%undefine cross_check_fips

Name: %{_cross_os}nitro-cli
Version: 1.4.4
Release: 1%{?dist}
Summary: AWS Nitro Enclaves CLI
License: Apache-2.0
URL: https://github.com/aws/aws-nitro-enclaves-cli

Source0: https://github.com/aws/aws-nitro-enclaves-cli/archive/refs/tags/v%{version}.tar.gz
Source1: bundled-v%{version}.tar.gz

Patch0001: 0001-use-aws-lc-rs-backend.patch

Source100: nitro-cli-sysusers.conf
Source200: nitro-cli-tmpfiles.conf

BuildRequires: %{_cross_os}glibc-devel

Requires: %{_cross_os}vsock-proxy

%description
%{summary}.

%prep
%setup -n aws-nitro-enclaves-cli-%{version} -q
%setup -T -D -a 1 -n aws-nitro-enclaves-cli-%{version}
%cargo_prep

# Use aws-lc backend for openssl crate
%patch -P 0001 -p1

# Use the updated Cargo.lock that includes aws-lc dependencies
cp Cargo.lock.updated Cargo.lock


%build
%cargo_build -p nitro-cli
%cargo_build -p vsock-proxy

%install
install -d %{buildroot}%{_cross_bindir}
install -p -m 0755 %{__cargo_outdir}/nitro-cli %{buildroot}%{_cross_bindir}/nitro-cli
install -p -m 0755 %{__cargo_outdir}/vsock-proxy %{buildroot}%{_cross_bindir}/vsock-proxy

install -d %{buildroot}%{_cross_sysusersdir}
install -p -m 0644 %{S:100} %{buildroot}%{_cross_sysusersdir}/nitro-cli.conf

install -d %{buildroot}%{_cross_tmpfilesdir}
install -p -m 0644 %{S:200} %{buildroot}%{_cross_tmpfilesdir}/nitro-cli.conf

%files
%license LICENSE NOTICE
%{_cross_attribution_file}
%{_cross_bindir}/nitro-cli
%{_cross_sysusersdir}/nitro-cli.conf
%{_cross_tmpfilesdir}/nitro-cli.conf

%package -n %{_cross_os}vsock-proxy
Summary: Vsock-to-TCP proxy for Nitro Enclaves

%description -n %{_cross_os}vsock-proxy
%{summary}.

%files -n %{_cross_os}vsock-proxy
%license LICENSE NOTICE
%{_cross_attribution_file}
%{_cross_bindir}/vsock-proxy
