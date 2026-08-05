import { OmiPerch } from './OmiPerch'
import { cn } from '@/lib/utils'

export interface OmiHeroProps {
  className?: string
  variant?: 'welcome' | 'login'
  size?: 'compact' | 'default'
  interactive?: boolean
}

export function OmiHero({
  className,
  variant = 'welcome',
  size = 'default',
  interactive = true,
}: OmiHeroProps) {
  return (
    <div
      className={cn(
        'relative flex items-end',
        variant === 'login' ? 'justify-start' : 'justify-center',
        className,
      )}
      aria-label="欧米品牌形象"
    >
      <div className="pointer-events-none absolute inset-x-[16%] top-[24%] h-[48%] rounded-full bg-brand-400/15 blur-2xl" />
      <OmiPerch
        interactive={interactive}
        className={cn(
          'relative',
          size === 'compact'
            ? 'w-36 sm:w-40'
            : variant === 'login'
              ? 'w-44 xl:w-52'
              : 'w-40 sm:w-52 lg:w-56',
        )}
      />
    </div>
  )
}
