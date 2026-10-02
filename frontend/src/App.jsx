import { useEffect, useState } from "react";
import ChatWidget from "./components/ChatWidget.jsx";
import ItemDrawer from "./components/ItemDrawer.jsx";
import { NAV, ServiceBanner, Sidebar, StatusPills } from "./components/Layout.jsx";
import { Toasts } from "./components/ui.jsx";
import { AppProvider } from "./context.jsx";
import Arquitetura from "./pages/Arquitetura.jsx";
import Cadastro from "./pages/Cadastro.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Movimentacoes from "./pages/Movimentacoes.jsx";
import Produtos from "./pages/Produtos.jsx";

const PAGES = { dashboard: Dashboard, produtos: Produtos, cadastro: Cadastro, movimentacoes: Movimentacoes, arquitetura: Arquitetura };

const pageFromHash = () => {
  const id = window.location.hash.replace("#/", "");
  return PAGES[id] ? id : "dashboard";
};

export default function App() {
  const [page, setPage] = useState(pageFromHash);

  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const navigate = (id) => {
    window.location.hash = `#/${id}`;
    setPage(id);
    window.scrollTo(0, 0);
  };

  const Page = PAGES[page];
  const title = NAV.find((n) => n.id === page)?.label;

  return (
    <AppProvider>
      <div className="layout">
        <Sidebar page={page} onNavigate={navigate} />
        <div className="content">
          <header className="topbar">
            <span className="crumb">Estoque Inteligente / <b>{title}</b></span>
            <StatusPills />
          </header>
          <ServiceBanner />
          <main key={page}>
            <Page onNavigate={navigate} />
          </main>
        </div>
      </div>
      <ItemDrawer />
      <ChatWidget />
      <Toasts />
    </AppProvider>
  );
}
