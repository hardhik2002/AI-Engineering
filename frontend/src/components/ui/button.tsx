import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva('ui-button', {
  variants: {
    variant: { default: 'ui-button-primary', secondary: 'ui-button-secondary', ghost: 'ui-button-ghost' },
    size: { default: 'ui-button-default', icon: 'ui-button-icon', small: 'ui-button-small' },
  },
  defaultVariants: { variant: 'default', size: 'default' },
})

export function Button({
  className, variant, size, asChild = false, ...props
}: React.ComponentProps<'button'> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Component = asChild ? Slot : 'button'
  return <Component data-slot="button" className={cn(buttonVariants({ variant, size }), className)} {...props} />
}

