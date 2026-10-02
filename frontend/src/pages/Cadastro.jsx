import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Hash, ImagePlus, Loader2, RotateCcw, Trash2, UploadCloud } from "lucide-react";
import { api, brl, notifyChanged } from "../api.js";
import { CurrencyInput, NumberStepper } from "../components/inputs.jsx";
import { ItemImage, PageHeader } from "../components/ui.jsx";
import { useApp } from "../context.jsx";

const EMPTY = { name: "", category: "", quantity: 0, min_quantity: 5, unit_price: 0 };
const MAX_BYTES = 5 * 1024 * 1024;
const TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];

export default function Cadastro({ onNavigate }) {
  const { toast, toastError, openItem, serviceStatus } = useApp();
  const [form, setForm] = useState(EMPTY);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [saving, setSaving] = useState(false);
  const [fieldError, setFieldError] = useState("");
  const [categories, setCategories] = useState([]);
  const [created, setCreated] = useState([]); // cadastrados nesta sessão
  const [pendingPhoto, setPendingPhoto] = useState(null); // item salvo cuja foto falhou
  const [skuPreview, setSkuPreview] = useState("");
  const inputRef = useRef(null);

  useEffect(() => { api.categories().then(setCategories).catch(() => {}); }, []);

  // Prévia do código que o sistema vai gerar (muda com a categoria)
  useEffect(() => {
    const t = setTimeout(() => {
      api.previewSku(form.category.trim()).then((r) => setSkuPreview(r.sku)).catch(() => setSkuPreview(""));
    }, 300);
    return () => clearTimeout(t);
  }, [form.category, created.length]);
  useEffect(() => () => preview && URL.revokeObjectURL(preview), [preview]);

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });
  const setValue = (field) => (value) => setForm({ ...form, [field]: value });

  const pickFile = (f) => {
    if (!f) return;
    if (!TYPES.includes(f.type)) return setFieldError("A foto precisa ser JPG, PNG, WEBP ou GIF.");
    if (f.size > MAX_BYTES) return setFieldError("A foto precisa ter no máximo 5 MB.");
    setFieldError("");
    setFile(f);
    setPreview(URL.createObjectURL(f));
  };

  const reset = () => {
    setForm({ ...EMPTY, category: form.category });
    setFile(null);
    setPreview(null);
  };

  const uploadPhoto = async (item, photo) => {
    try {
      const updated = await api.uploadImage(item.id, photo);
      setPendingPhoto(null);
      return updated;
    } catch (err) {
      // O item já foi salvo no banco: avisamos e deixamos tentar de novo
      setPendingPhoto({ item, file: photo });
      toastError(err, "Produto salvo, mas a foto não foi enviada");
      return item;
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!(form.unit_price > 0)) {
      setFieldError("Informe o preço unitário.");
      return;
    }
    setSaving(true);
    setFieldError("");
    try {
      // Sem SKU: o sistema gera o código a partir da categoria
      let item = await api.createItem({ ...form, name: form.name.trim(), category: form.category.trim() || "Geral" });
      if (file) item = await uploadPhoto(item, file);
      setCreated((c) => [item, ...c].slice(0, 6));
      toast("success", `Produto cadastrado: ${item.sku}`, `${item.name} foi salvo no banco${file && item.image_url ? " e a foto no S3" : ""}.`);
      notifyChanged();
      reset();
    } catch (err) {
      if (err.status === 409 || err.status === 422) setFieldError(err.message);
      else toastError(err, "Não foi possível cadastrar");
    } finally {
      setSaving(false);
    }
  };

  const retryPhoto = async () => {
    const updated = await uploadPhoto(pendingPhoto.item, pendingPhoto.file);
    if (updated.image_url) {
      setCreated((c) => c.map((i) => (i.id === updated.id ? updated : i)));
      toast("success", "Foto enviada", "A foto foi salva no S3.");
      notifyChanged();
    }
  };

  const s3Down = serviceStatus("s3") === "down";

  return (
    <>
      <PageHeader title="Cadastro de produtos" subtitle="Cadastre produtos com foto. Os dados e a foto vão para o Amazon S3." />

      {pendingPhoto && (
        <div className="callout warning">
          <span>A foto de <b>{pendingPhoto.item.name}</b> não foi enviada (S3 indisponível). O produto já está salvo.</span>
          <button className="btn" onClick={retryPhoto}><RotateCcw size={16} /> Reenviar foto</button>
        </div>
      )}

      <form className="register" onSubmit={submit}>
        <div className="card">
          <h2>Dados do produto</h2>
          <div className="form-grid">
            <label className="full">Nome do produto *<input required maxLength={120} value={form.name} onChange={set("name")} placeholder="Ex.: Fone Bluetooth JBL" /></label>
            <label>Categoria
              <input list="categorias" value={form.category} onChange={set("category")} placeholder="Ex.: Áudio" />
              <datalist id="categorias">{categories.map((c) => <option key={c} value={c} />)}</datalist>
            </label>
            <div className="field">
              <span className="field-label">Código (SKU)</span>
              <div className="sku-preview">
                <Hash size={15} /> <b>{skuPreview || "—"}</b>
                <small>gerado automaticamente</small>
              </div>
            </div>
            <label>Preço unitário *
              <CurrencyInput value={form.unit_price} onChange={setValue("unit_price")} required />
            </label>
            <div className="field">
              <span className="field-label">Valor em estoque</span>
              <div className="computed">{brl(form.unit_price * form.quantity)}</div>
            </div>
            <label>Quantidade inicial
              <NumberStepper value={form.quantity} onChange={setValue("quantity")} />
            </label>
            <label>Estoque mínimo
              <NumberStepper value={form.min_quantity} onChange={setValue("min_quantity")} />
            </label>
          </div>
          {fieldError && <div className="field-error">{fieldError}</div>}
        </div>

        <div className="card">
          <h2>Foto</h2>
          <div
            className={`dropzone ${dragging ? "dragging" : ""} ${preview ? "has-file" : ""}`}
            onClick={() => inputRef.current.click()}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); pickFile(e.dataTransfer.files[0]); }}
          >
            {preview ? (
              <img src={preview} alt="Pré-visualização" />
            ) : (
              <>
                <UploadCloud size={36} />
                <strong>Arraste a foto aqui</strong>
                <span className="muted">ou clique para escolher · JPG, PNG, WEBP · até 5 MB</span>
              </>
            )}
            <input ref={inputRef} type="file" accept={TYPES.join(",")} hidden onChange={(e) => pickFile(e.target.files[0])} />
          </div>
          {preview && (
            <div className="row-between file-info">
              <span className="muted"><ImagePlus size={14} /> {file.name} · {(file.size / 1024).toFixed(0)} KB</span>
              <button type="button" className="link-btn" onClick={() => { setFile(null); setPreview(null); }}><Trash2 size={14} /> Remover</button>
            </div>
          )}
          {s3Down && <p className="hint warning">⚠ O S3 está fora do ar: o produto será salvo, mas a foto ficará pendente.</p>}
        </div>

        <div className="form-actions">
          <button type="button" className="btn" onClick={reset}>Limpar</button>
          <button className="btn primary" disabled={saving}>
            {saving ? <><Loader2 size={16} className="spin" /> Salvando…</> : <><CheckCircle2 size={16} /> Cadastrar produto</>}
          </button>
        </div>
      </form>

      {created.length > 0 && (
        <div className="card">
          <div className="card-title">
            <h2>Cadastrados agora</h2>
            <button className="link-btn" onClick={() => onNavigate("produtos")}>Ver catálogo →</button>
          </div>
          <div className="created-list">
            {created.map((i) => (
              <button key={i.id} className="created" onClick={() => openItem(i.id)}>
                <ItemImage item={i} size="sm" />
                <span><b>{i.name}</b><small className="muted">{i.sku} · {brl(i.unit_price)} · {i.quantity} un.</small></span>
              </button>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
