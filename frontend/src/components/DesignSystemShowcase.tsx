import React, { useState } from "react";
import {
  Button,
  Card,
  Badge,
  Alert,
  FormField,
  TextInput,
  TextArea,
  Select,
  Checkbox,
} from "../ui";

export function DesignSystemShowcase() {
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    specialty: "",
    bio: "",
    termsAccepted: false,
  });

  const [showAlert, setShowAlert] = useState(true);
  const [submitSuccess, setSubmitSuccess] = useState(false);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    const { name, value, type } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]:
        type === "checkbox" ? (e.target as HTMLInputElement).checked : value,
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (formData.name && formData.email && formData.termsAccepted) {
      setSubmitSuccess(true);
      setTimeout(() => setSubmitSuccess(false), 3000);
    }
  };

  return (
    <div className="p-8 bg-[var(--atlas-background)] min-h-screen">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-4xl font-bold text-[var(--atlas-text-primary)] mb-2">
          Atlas Design System
        </h1>
        <p className="text-lg text-[var(--atlas-text-secondary)] mb-12">
          Consultorio Médico - Phase 1 Components
        </p>

        {/* ALERTS SECTION */}
        <section className="mb-12">
          <h2 className="text-2xl font-semibold text-[var(--atlas-text-primary)] mb-6">
            Alerts
          </h2>
          <div className="space-y-4">
            {showAlert && (
              <Alert
                type="info"
                title="Welcome to Atlas"
                onClose={() => setShowAlert(false)}
              >
                Este es el Design System oficial. Todos los componentes están
                construidos con Tailwind 4 y variables CSS.
              </Alert>
            )}

            <Alert type="success" title="Éxito">
              La operación se completó correctamente.
            </Alert>

            <Alert type="warning" title="Advertencia">
              Por favor revisa los datos antes de continuar.
            </Alert>

            <Alert type="danger" title="Error">
              Ocurrió un problema. Intenta nuevamente.
            </Alert>
          </div>
        </section>

        {/* BADGES SECTION */}
        <section className="mb-12">
          <h2 className="text-2xl font-semibold text-[var(--atlas-text-primary)] mb-6">
            Badges
          </h2>
          <div className="flex flex-wrap gap-3">
            <Badge status="default">Default</Badge>
            <Badge status="success">Activo</Badge>
            <Badge status="warning">Pendiente</Badge>
            <Badge status="danger">Crítico</Badge>
            <Badge status="info">Información</Badge>
          </div>
        </section>

        {/* BUTTONS SECTION */}
        <section className="mb-12">
          <h2 className="text-2xl font-semibold text-[var(--atlas-text-primary)] mb-6">
            Buttons
          </h2>

          <div className="space-y-6">
            {/* Primary Buttons */}
            <div>
              <p className="text-sm font-semibold text-[var(--atlas-text-secondary)] mb-3">
                Primary
              </p>
              <div className="flex flex-wrap gap-3">
                <Button size="sm">Small</Button>
                <Button size="md">Medium</Button>
                <Button size="lg">Large</Button>
                <Button disabled>Disabled</Button>
                <Button isLoading>Loading...</Button>
              </div>
            </div>

            {/* Secondary Buttons */}
            <div>
              <p className="text-sm font-semibold text-[var(--atlas-text-secondary)] mb-3">
                Secondary
              </p>
              <div className="flex flex-wrap gap-3">
                <Button variant="secondary" size="sm">
                  Small
                </Button>
                <Button variant="secondary" size="md">
                  Medium
                </Button>
                <Button variant="secondary" size="lg">
                  Large
                </Button>
                <Button variant="secondary" disabled>
                  Disabled
                </Button>
              </div>
            </div>

            {/* Ghost Buttons */}
            <div>
              <p className="text-sm font-semibold text-[var(--atlas-text-secondary)] mb-3">
                Ghost
              </p>
              <div className="flex flex-wrap gap-3">
                <Button variant="ghost" size="sm">
                  Small
                </Button>
                <Button variant="ghost" size="md">
                  Medium
                </Button>
                <Button variant="ghost" size="lg">
                  Large
                </Button>
              </div>
            </div>

            {/* Danger Buttons */}
            <div>
              <p className="text-sm font-semibold text-[var(--atlas-text-secondary)] mb-3">
                Danger
              </p>
              <div className="flex flex-wrap gap-3">
                <Button variant="danger" size="sm">
                  Delete
                </Button>
                <Button variant="danger" size="md">
                  Remove
                </Button>
                <Button variant="danger" size="lg">
                  Cancel
                </Button>
              </div>
            </div>
          </div>
        </section>

        {/* CARDS & FORMS SECTION */}
        <section>
          <h2 className="text-2xl font-semibold text-[var(--atlas-text-primary)] mb-6">
            Forms & Cards
          </h2>

          <Card>
            <h3 className="text-xl font-semibold text-[var(--atlas-text-primary)] mb-6">
              Medical Professional Registration
            </h3>

            {submitSuccess && (
              <Alert type="success" className="mb-6">
                ¡Registro completado exitosamente!
              </Alert>
            )}

            <form onSubmit={handleSubmit} className="space-y-6">
              <FormField
                label="Full Name"
                required
                error={
                  formData.name === ""
                    ? "Name is required"
                    : ""
                }
                helperText="Enter your full legal name"
              >
                <TextInput
                  name="name"
                  placeholder="John Doe"
                  value={formData.name}
                  onChange={handleChange}
                  error={formData.name === ""}
                />
              </FormField>

              <FormField
                label="Email Address"
                required
                error={
                  formData.email === ""
                    ? "Email is required"
                    : ""
                }
              >
                <TextInput
                  name="email"
                  type="email"
                  placeholder="john@example.com"
                  value={formData.email}
                  onChange={handleChange}
                  error={formData.email === ""}
                />
              </FormField>

              <FormField label="Medical Specialty" helperText="Select your primary specialty">
                <Select
                  name="specialty"
                  value={formData.specialty}
                  onChange={handleChange}
                  options={[
                    { value: "", label: "Choose a specialty" },
                    { value: "cardiology", label: "Cardiología" },
                    { value: "pediatrics", label: "Pediatría" },
                    { value: "neurology", label: "Neurología" },
                    { value: "dermatology", label: "Dermatología" },
                  ]}
                />
              </FormField>

              <FormField
                label="Professional Bio"
                helperText="Brief description of your experience"
              >
                <TextArea
                  name="bio"
                  placeholder="Tell us about your medical background..."
                  value={formData.bio}
                  onChange={handleChange}
                  rows={4}
                />
              </FormField>

              <div className="pt-4">
                <Checkbox
                  name="termsAccepted"
                  label="I agree to the terms and conditions"
                  checked={formData.termsAccepted}
                  onChange={handleChange}
                />
              </div>

              <div className="flex gap-3 pt-6">
                <Button type="submit">Register Professional</Button>
                <Button type="reset" variant="secondary">
                  Clear Form
                </Button>
              </div>
            </form>
          </Card>
        </section>
      </div>
    </div>
  );
}

export default DesignSystemShowcase;
