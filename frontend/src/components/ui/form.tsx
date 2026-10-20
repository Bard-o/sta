// Formulario de shadcn/ui (react-hook-form) pintado con las clases sta-field del sistema de diseño.
import { createContext, useContext, useId, type ComponentProps } from "react";
import { Slot } from "radix-ui";
import {
  Controller,
  FormProvider,
  useFormContext,
  useFormState,
  type ControllerProps,
  type FieldPath,
  type FieldValues,
} from "react-hook-form";
import { cn } from "@/lib/utils";
import { Icon } from "./icon";
import { Label } from "./label";

export const Form = FormProvider;

type FormFieldContextValue = { name: string };
const FormFieldContext = createContext<FormFieldContextValue | null>(null);

type FormItemContextValue = { id: string };
const FormItemContext = createContext<FormItemContextValue | null>(null);

export function FormField<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
>(props: ControllerProps<TFieldValues, TName>) {
  return (
    <FormFieldContext.Provider value={{ name: props.name }}>
      <Controller {...props} />
    </FormFieldContext.Provider>
  );
}

function useFormField() {
  const fieldContext = useContext(FormFieldContext);
  const itemContext = useContext(FormItemContext);
  if (!fieldContext || !itemContext) {
    throw new Error("useFormField debe usarse dentro de <FormField> y <FormItem>.");
  }
  const { getFieldState } = useFormContext();
  const formState = useFormState({ name: fieldContext.name });
  const fieldState = getFieldState(fieldContext.name, formState);
  const { id } = itemContext;
  return {
    id,
    name: fieldContext.name,
    formItemId: `${id}-control`,
    formMessageId: `${id}-m`,
    ...fieldState,
  };
}

function FormItemShell({ className, ...props }: ComponentProps<"div">) {
  const { error } = useFormField();
  return <div className={cn("sta-field", error && "sta-field--error", className)} {...props} />;
}

export function FormItem(props: ComponentProps<"div">) {
  const id = useId();
  return (
    <FormItemContext.Provider value={{ id }}>
      <FormItemShell {...props} />
    </FormItemContext.Provider>
  );
}

export function FormLabel(props: ComponentProps<typeof Label>) {
  const { formItemId } = useFormField();
  return <Label htmlFor={formItemId} {...props} />;
}

export function FormControl(props: ComponentProps<typeof Slot.Root>) {
  const { error, formItemId, formMessageId } = useFormField();
  return (
    <div className="sta-field__control">
      <Slot.Root
        id={formItemId}
        aria-describedby={error ? formMessageId : undefined}
        aria-invalid={!!error}
        {...props}
      />
    </div>
  );
}

/** Ayuda bajo el campo; si hay error, se muestra el error en su lugar. */
export function FormDescription({ className, ...props }: ComponentProps<"div">) {
  const { error, formMessageId } = useFormField();
  if (error) return null;
  return <div id={formMessageId} className={cn("sta-field__msg", className)} {...props} />;
}

/** Error junto al campo, en español y diciendo cómo corregirlo (IU-07). */
export function FormMessage({ className, children, ...props }: ComponentProps<"div">) {
  const { error, formMessageId } = useFormField();
  const body = error ? String(error.message ?? "") : children;
  if (!body) return null;
  return (
    <div
      id={formMessageId}
      role={error ? "alert" : undefined}
      className={cn("sta-field__msg", className)}
      {...props}
    >
      {error && <Icon name="alert" />}
      {body}
    </div>
  );
}
